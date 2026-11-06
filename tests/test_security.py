from __future__ import annotations

import concurrent.futures
import dataclasses
import hashlib
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
from config import load_config
from filestore import DiskFileStore, QuotaExceeded
from ratelimiter import RateLimiter
from uploads import CHUNK_SIZE, InvalidUpload, receive_upload

from app import BoundedThreadingServer, load_templates, make_handler


def multipart(data: bytes, filename: str = "report.txt", field: str = "file") -> bytes:
    return (
        f'--boundary\r\nContent-Disposition: form-data; name="{field}"; '
        f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
        + data
        + b"\r\n--boundary--\r\n"
    )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = dataclasses.replace(
            load_config(str(APP)),
            upload_dir=str(self.root / "uploads"),
            files_db=str(self.root / "data/db.json"),
            public_base_url="",
            trusted_proxies=(),
            rate_limit_seconds=0,
            request_timeout_seconds=1,
            max_upload_mb=1,
        )
        self.store = DiskFileStore(self.cfg.upload_dir, self.cfg.files_db)
        self.server = None

    def start(self, **overrides):
        self.cfg = dataclasses.replace(self.cfg, **overrides)
        handler = make_handler(
            self.store,
            RateLimiter(self.cfg.rate_limit_seconds),
            load_templates(str(APP)),
            self.cfg,
            str(APP),
        )
        handler.log_message = lambda *args: None
        self.server = BoundedThreadingServer(("127.0.0.1", 0), handler, self.cfg.max_connections)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def request(self, path, data=None, headers=None, method=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(
            method or ("POST" if data is not None else "GET"),
            path,
            body=data,
            headers=headers or {},
        )
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
        self.tmp.cleanup()

    def test_path_traversal_absolute_unregistered_and_symlink_rejected(self):
        self.start()
        outside = self.root / "private.txt"
        outside.write_bytes(b"not public")
        self.store.store("127.0.0.1", "safe.txt", b"safe")
        Path(self.cfg.upload_dir, "link.txt").symlink_to(outside)
        for name in (
            "..%2Fprivate.txt",
            "%2Fetc%2Fpasswd",
            "..%5Cprivate.txt",
            "%00",
            "%252e%252e%252fprivate.txt",
            "link.txt",
            "unknown.txt",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.request("/download/" + name)[0], 404)
        self.assertEqual(self.request("/download/safe.txt")[2], b"safe")

    def test_raw_and_multipart_round_trip_with_unicode_name(self):
        self.start()
        for body, headers in (
            (b"raw", {}),
            (
                multipart(b"content", "résumé.txt"),
                {"Content-Type": "multipart/form-data; boundary=boundary"},
            ),
        ):
            status, _, response = self.request("/upload", body, headers)
            self.assertEqual(status, 200, response)
            path = urlsplit(response.decode().splitlines()[0]).path
            status, response_headers, content = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(content, b"raw" if body == b"raw" else b"content")
            self.assertEqual(int(response_headers["Content-Length"]), len(content))
            self.assertIn("filename*=UTF-8''", response_headers["Content-Disposition"])

    def test_spoofed_ip_cannot_clear_or_list_another_ip(self):
        self.store.store("203.0.113.7", "victim-private.txt", b"private")
        self.start()
        forged = {"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "203.0.113.7"}
        self.assertNotIn(b"victim-private", self.request("/uploads", headers=forged)[2])
        self.assertEqual(self.request("/clear", b"", forged)[0], 200)
        self.assertEqual(len(self.store.list_by_ip("203.0.113.7")), 1)

    def test_trusted_proxy_and_xff_walk(self):
        self.store.store("203.0.113.7", "owner.txt", b"private")
        self.start(trusted_proxies=("127.0.0.1/32",))
        self.assertIn(
            b"owner.txt",
            self.request(
                "/uploads", headers={"X-Forwarded-For": "198.51.100.8, 203.0.113.7, 127.0.0.1"}
            )[2],
        )
        self.assertNotIn(
            b"owner.txt", self.request("/uploads", headers={"X-Real-IP": "invalid"})[2]
        )
        self.request("/clear", b"", {"X-Real-IP": "203.0.113.7"})
        self.assertFalse(self.store.list_by_ip("203.0.113.7"))

    def test_listing_is_per_ip_without_public_ip_or_country_columns(self):
        self.store.store("127.0.0.1", "mine.txt", b"mine")
        self.store.store("203.0.113.7", "someone-elses.txt", b"other")
        self.start()
        body = self.request("/uploads")[2]
        self.assertIn(b"mine.txt", body)
        self.assertNotIn(b"someone-elses", body)
        self.assertNotIn(b"203.0.113.7", body)
        self.assertNotIn(b"<th>IP</th>", body)
        self.assertNotIn(b"flagcdn", body)

    def test_size_rejected_before_body_is_read(self):
        self.start()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.putrequest("POST", "/upload")
        connection.putheader("Content-Length", 2 * 1024**2)
        connection.endheaders()  # Deliberately send no body.
        self.assertEqual(connection.getresponse().status, 413)
        connection.close()
        self.assertFalse(list(Path(self.cfg.upload_dir).iterdir()))

    def test_request_length_validation(self):
        self.start()
        for header, expected in (
            ("", 411),
            ("Content-Length: -1\r\n", 400),
            ("Content-Length: nope\r\n", 400),
            ("Content-Length: 0\r\nContent-Length: 0\r\n", 400),
            ("Transfer-Encoding: chunked\r\n", 400),
        ):
            with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
                sock.sendall(("POST /upload HTTP/1.0\r\n" + header + "\r\n").encode())
                self.assertIn(str(expected).encode(), sock.recv(4096).split(b"\r\n")[0])

    def test_malformed_multipart_is_not_committed(self):
        self.start()
        for data in (
            multipart(b"x")[:-20],
            multipart(b"x", field="not-file"),
            multipart(b"x").replace(b"--boundary--", b"--boundary\r\n"),
        ):
            status, _, _ = self.request(
                "/upload", data, {"Content-Type": "multipart/form-data; boundary=boundary"}
            )
            self.assertEqual(status, 400)
        self.assertEqual(self.store.entries(), {})
        self.assertFalse(list(Path(self.cfg.upload_dir).glob(".incoming-*")))

    def test_filename_paths_controls_and_html_are_sanitized(self):
        self.start()
        status, _, response = self.request(
            "/upload",
            multipart(b"x", "../../<script>.txt"),
            {"Content-Type": "multipart/form-data; boundary=boundary"},
        )
        self.assertEqual(status, 200, response)
        listing = self.request("/uploads")[2]
        self.assertIn(b"&lt;script&gt;.txt", listing)
        self.assertNotIn(b"<script>.txt", listing)
        filename = next(iter(self.store.entries().values()))[0].filename
        self.assertNotIn("/", filename)

    def test_cooldown_returns_retry_after(self):
        self.start(rate_limit_seconds=2)
        self.assertEqual(self.request("/upload", b"one")[0], 200)
        status, headers, _ = self.request("/upload", b"two", {"X-Real-IP": "203.0.113.9"})
        self.assertEqual(status, 429)
        self.assertIn(headers["Retry-After"], ("1", "2"))

    def test_expiry_checked_on_download_before_cleanup_tick(self):
        self.store.store("127.0.0.1", "expired.txt", b"expired")
        path = Path(self.cfg.files_db)
        data = json.loads(path.read_text())
        data["127.0.0.1"][0]["time"] = 1
        path.write_text(json.dumps(data))
        self.start()
        self.assertEqual(self.request("/download/expired.txt")[0], 404)
        self.assertNotIn(b"expired.txt", self.request("/uploads")[2])
        self.assertEqual(self.store.delete_expired(3600), 1)

    def test_cross_site_clear_is_rejected(self):
        self.start()
        self.assertEqual(self.request("/clear", b"", {"Origin": "https://other.example"})[0], 403)

    def test_slow_upload_does_not_block_health_request(self):
        self.start()
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
            sock.sendall(b"POST /upload HTTP/1.0\r\nContent-Length: 100\r\n\r\nx")
            begin = time.monotonic()
            self.assertEqual(self.request("/robots.txt")[0], 200)
            self.assertLess(time.monotonic() - begin, 0.8)
            self.assertIn(b"408", sock.recv(4096).split(b"\r\n")[0])
        self.assertFalse(self.store.entries())

    def test_connection_limit_returns_503(self):
        self.start(max_connections=1)
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
            sock.sendall(b"POST /upload HTTP/1.0\r\nContent-Length: 100\r\n\r\nx")
            time.sleep(0.05)
            self.assertEqual(self.request("/robots.txt")[0], 503)
        time.sleep(0.05)

    def test_host_is_not_injected_into_html_or_script(self):
        self.start()
        malicious = {"Host": 'evil.example"><script>alert(1)</script>'}
        self.assertNotIn(b"<script>alert(1)", self.request("/", headers=malicious)[2])
        self.assertNotIn(b"<script>alert(1)", self.request("/upload.sh", headers=malicious)[2])

    def test_concurrent_store_cleanup_preserves_metadata(self):
        def save(index):
            self.store.store("127.0.0.1", f"{index}.txt", b"x")
            self.store.delete_expired(3600)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(save, range(50)))
        self.assertEqual(len(self.store.list_by_ip("127.0.0.1")), 50)
        self.assertEqual(self.store.used_bytes_by_ip("127.0.0.1"), 50)

    def test_atomic_metadata_failure_preserves_previous_json(self):
        self.store.store("127.0.0.1", "one.txt", b"one")
        before = Path(self.cfg.files_db).read_bytes()
        with patch("filestore.json.dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.store("127.0.0.1", "two.txt", b"two")
        self.assertEqual(Path(self.cfg.files_db).read_bytes(), before)
        self.assertFalse(Path(self.cfg.upload_dir, "two.txt").exists())

    def test_concurrent_quota_reservations_are_counted_and_released(self):
        with self.store.reserve("one", 60, 100, 100):
            with self.assertRaises(QuotaExceeded):
                with self.store.reserve("two", 50, 100, 100):
                    pass
            with self.assertRaises(QuotaExceeded):
                with self.store.reserve("one", 50, 200, 100):
                    pass
        with self.store.reserve("two", 100, 100, 100):
            pass

    def test_corrupt_metadata_is_not_silently_reset(self):
        Path(self.cfg.files_db).write_text("{broken")
        with self.assertRaises(json.JSONDecodeError):
            DiskFileStore(self.cfg.upload_dir, self.cfg.files_db)


class StreamingTests(unittest.TestCase):
    def test_streamed_raw_upload_has_bounded_memory(self):
        class GeneratedStream:
            def read(self, size):
                if size > CHUNK_SIZE:
                    raise AssertionError("Unbounded read")
                return b"x" * size

        with tempfile.TemporaryFile("w+b") as target:
            tracemalloc.start()
            receive_upload(
                GeneratedStream(), target, "application/octet-stream", 16 * 1024**2, 32 * 1024**2
            )
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, 1024**2)
            self.assertEqual(target.tell(), 16 * 1024**2)

    def test_multipart_streaming_across_chunk_boundaries(self):
        data = os.urandom(2 * CHUNK_SIZE + 5)
        with tempfile.TemporaryFile("w+b") as target:
            name, size = receive_upload(
                io.BytesIO(multipart(data)),
                target,
                "multipart/form-data; boundary=boundary",
                len(multipart(data)),
                1024**2,
            )
            target.seek(0)
            self.assertEqual(hashlib.sha256(target.read()).digest(), hashlib.sha256(data).digest())
            self.assertEqual((name, size), ("report.txt", len(data)))

    def test_multipart_file_limit_and_missing_boundary(self):
        for body, content_type in (
            (multipart(b"12345"), "multipart/form-data; boundary=boundary"),
            (multipart(b"x"), "multipart/form-data"),
        ):
            with self.assertRaises(InvalidUpload):
                receive_upload(io.BytesIO(body), io.BytesIO(), content_type, len(body), 4)


if __name__ == "__main__":
    unittest.main()
