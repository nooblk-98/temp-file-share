from __future__ import annotations

import datetime
import http.server
import ipaddress
import logging
import math
import os
import re
import shutil
import socketserver
import tempfile
import threading
import time
import urllib.parse
import uuid
from html import escape

from config import load_config
from filestore import DiskFileStore, QuotaExceeded
from models import Config, IPAddress
from ratelimiter import RateLimiter
from uploads import CHUNK_SIZE, MULTIPART_OVERHEAD, InvalidUpload, UploadTooLarge, receive_upload

logger = logging.getLogger("temp-file-share")


def trusted_peer(handler: http.server.BaseHTTPRequestHandler, config: Config) -> bool:
    peer = ipaddress.ip_address(handler.client_address[0])
    return any(
        peer in ipaddress.ip_network(network, strict=False) for network in config.trusted_proxies
    )


def get_client_ip(handler: http.server.BaseHTTPRequestHandler, config: Config) -> IPAddress:
    peer = IPAddress(handler.client_address[0])
    if not trusted_peer(handler, config):
        return peer
    real = handler.headers.get("X-Real-IP")
    if real:
        try:
            return IPAddress(str(ipaddress.ip_address(real.strip())))
        except ValueError:
            return peer
    chain = handler.headers.get("X-Forwarded-For", "").split(",")
    # Walk from the nearest proxy, not the attacker-controlled leftmost entry.
    for value in reversed(chain):
        try:
            candidate = ipaddress.ip_address(value.strip())
        except ValueError:
            return peer
        if not any(
            candidate in ipaddress.ip_network(n, strict=False) for n in config.trusted_proxies
        ):
            return IPAddress(str(candidate))
    return peer


def safe_upload_name(value: str | None) -> str | None:
    if not value:
        return None
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c.isprintable() and c not in "\r\n\x00")
    # Leave room for UUID and stay below common filesystem byte limits.
    return name.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "upload.bin"


def clean_display_name(filename: str) -> str:
    if (
        len(filename) > 33
        and filename[32] == "_"
        and all(c in "0123456789abcdef" for c in filename[:32])
    ):
        return filename[33:]
    return filename


def get_public_base_url(handler: http.server.BaseHTTPRequestHandler, config: Config) -> str:
    if config.public_base_url:
        return config.public_base_url.rstrip("/")
    scheme = "http"
    if trusted_peer(handler, config) and handler.headers.get("X-Forwarded-Proto") == "https":
        scheme = "https"
    host = handler.headers.get("Host", f"localhost:{config.port}")
    if not re.fullmatch(r"(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\])(?::[0-9]{1,5})?", host):
        host = f"localhost:{config.port}"
    return f"{scheme}://{host}"


def load_templates(base_dir: str) -> dict[str, str]:
    template_names = {
        "index": "index.html",
        "uploads": "uploads.html",
        "robots": "robots.txt",
        "sitemap": "sitemap.xml",
    }
    templates: dict[str, str] = {}
    for key, filename in template_names.items():
        path = os.path.join(base_dir, "templates", filename)
        with open(path) as f:
            templates[key] = f.read()
    script_path = os.path.join(base_dir, "scripts", "upload.sh")
    with open(script_path) as f:
        templates["upload_script"] = f.read()
    return templates


def make_handler(
    store: DiskFileStore,
    limiter: RateLimiter,
    templates: dict[str, str],
    config: Config,
    base_dir: str,
) -> type[http.server.BaseHTTPRequestHandler]:

    upload_dir = os.path.join(base_dir, config.upload_dir)
    max_age_seconds = config.max_age_hours * 3600
    max_storage_bytes = config.max_storage_gb * 1024**3
    ip_limit_bytes = config.ip_limit_gb * 1024**3
    static_dir = os.path.join(base_dir, "static")

    class Handler(http.server.BaseHTTPRequestHandler):
        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def safe_write(self, data: bytes) -> bool:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        def setup(self) -> None:
            self.request.settimeout(config.request_timeout_seconds)
            super().setup()

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self) -> None:
            client_ip = get_client_ip(self, config)
            if self.path not in ("/upload", "/clear"):
                self.send_error(404)
                return
            if self.path == "/clear":
                origin = self.headers.get("Origin")
                if self.headers.get("Sec-Fetch-Site") == "cross-site" or (
                    origin and origin.rstrip("/") != get_public_base_url(self, config)
                ):
                    self.send_error(403, "Cross-site clear requests are not allowed")
                    return
                freed = store.delete_by_ip(client_ip)
                logger.info("Clear: Freed files=%d", freed)
                self.send_response(200)
                self.end_headers()
                self.safe_write(b"Cleared uploads associated with your IP.")
                return

            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding"):
                self.send_error(400, "Transfer-Encoding is not supported")
                return
            if not lengths:
                self.send_error(411, "Content-Length required")
                return
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,20}", lengths[0]):
                self.send_error(400, "Invalid Content-Length")
                return
            content_length = int(lengths[0])
            content_type = self.headers.get("Content-Type", "application/octet-stream")
            max_file_size = config.max_upload_mb * 1024**2
            overhead = (
                MULTIPART_OVERHEAD if content_type.lower().startswith("multipart/form-data") else 0
            )
            if content_length > max_file_size + overhead:
                self.send_error(413, "Upload exceeds MAX_UPLOAD_MB")
                return
            delay = limiter.retry_after(client_ip)
            if delay:
                self.send_response(429)
                self.send_header("Retry-After", str(math.ceil(delay)))
                self.end_headers()
                self.safe_write(b"Upload cooldown active. Please retry after the indicated delay.")
                return

            temporary = None
            try:
                store.delete_expired(max_age_seconds)
                with store.reserve(client_ip, content_length, max_storage_bytes, ip_limit_bytes):
                    fd, temporary = tempfile.mkstemp(prefix=".incoming-", dir=upload_dir)
                    try:
                        with os.fdopen(fd, "wb") as target:
                            orig_name, file_size = receive_upload(
                                self.rfile, target, content_type, content_length, max_file_size
                            )
                        orig_name = safe_upload_name(orig_name)
                        filename = f"{uuid.uuid4().hex}_{orig_name or 'upload.bin'}"
                        store.commit(client_ip, filename, temporary)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
            except (QuotaExceeded, UploadTooLarge) as error:
                self.send_error(413, str(error))
                return
            except (InvalidUpload, ValueError) as error:
                self.send_error(400, str(error))
                return
            except (TimeoutError, ConnectionError):
                self.send_error(408, "Incomplete or timed-out upload")
                return
            except OSError:
                logger.exception("Upload storage failure")
                self.send_error(507, "Unable to store upload")
                return
            logger.info("Upload: File=%s, Size=%d", filename, file_size)

            disk_free = shutil.disk_usage(upload_dir).free
            allocated_remaining = max_storage_bytes - store.used_bytes()
            ip_remaining = ip_limit_bytes - store.used_bytes_by_ip(client_ip)
            expire_time = time.time() + max_age_seconds
            expire_str = datetime.datetime.fromtimestamp(expire_time).strftime("%Y-%m-%d %H:%M:%S")

            base_url = get_public_base_url(self, config)
            encoded_filename = urllib.parse.quote(filename, safe="")
            public_download = (
                f"{base_url}/download/{encoded_filename}"
                if base_url
                else f"/download/{encoded_filename}"
            )
            response = (
                f"{public_download}\n"
                f"Your IP: {client_ip}\n"
                f"File size: {file_size / 1024**2:.2f} MB\n"
                f"Expires: {expire_str}\n"
                f"Disk space left: {disk_free / 1024**3:.2f} GB\n"
                f"Allocated space remaining: {allocated_remaining / 1024**3:.2f} GB\n"
                f"IP limit remaining: {ip_remaining / 1024**3:.2f} GB"
            )
            self.send_response(200)
            self.end_headers()
            self.safe_write(response.encode())

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                used_bytes = store.used_bytes()
                used_gb = used_bytes / 1024**3
                percentage = (
                    (used_gb / config.max_storage_gb) * 100 if config.max_storage_gb > 0 else 0
                )
                client_ip = get_client_ip(self, config)
                ip_used_gb = store.used_bytes_by_ip(client_ip) / 1024**3
                ip_percentage = (
                    (ip_used_gb / config.ip_limit_gb) * 100 if config.ip_limit_gb > 0 else 0
                )
                recent_html = self._recent_uploads_html(client_ip)
                base_url = escape(get_public_base_url(self, config), quote=True)
                html = templates["index"].format(
                    used_gb=used_gb,
                    total_gb=config.max_storage_gb,
                    percentage=percentage,
                    ip_used_gb=ip_used_gb,
                    ip_percentage=ip_percentage,
                    max_age_hours=config.max_age_hours,
                    ip_limit_gb=config.ip_limit_gb,
                    max_upload_mb=config.max_upload_mb,
                    public_base_url=base_url,
                    base_url=base_url,
                    recent_uploads_html=recent_html,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.safe_write(html.encode())

            elif self.path in ("/uploads", "/uploads.html"):
                client_ip = get_client_ip(self, config)
                recent_html = self._recent_uploads_html(client_ip)
                base_url = escape(get_public_base_url(self, config), quote=True)
                html = templates["uploads"].format(
                    base_url=base_url,
                    recent_uploads_html=recent_html,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.safe_write(html.encode())

            elif self.path == "/robots.txt":
                base_url = get_public_base_url(self, config)
                content = templates["robots"].format(base_url=base_url)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.safe_write(content.encode("utf-8"))

            elif self.path == "/sitemap.xml":
                base_url = get_public_base_url(self, config)
                lastmod = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                content = templates["sitemap"].format(base_url=base_url, lastmod=lastmod)
                self.send_response(200)
                self.send_header("Content-Type", "application/xml; charset=utf-8")
                self.end_headers()
                self.safe_write(content.encode("utf-8"))

            elif self.path == "/upload.sh":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Disposition", 'attachment; filename="upload.sh"')
                self.end_headers()
                script = templates["upload_script"].replace(
                    "https://fs.app.itsnooblk.com", get_public_base_url(self, config)
                )
                self.safe_write(script.encode())

            elif self.path.startswith("/static/"):
                rel_path = self.path[len("/static/") :]
                if rel_path not in ("styles.css", "app.js"):
                    self.send_error(404)
                    return
                file_path = os.path.join(static_dir, rel_path)
                if not os.path.exists(file_path):
                    self.send_error(404)
                    return
                content_type = "text/css" if rel_path.endswith(".css") else "application/javascript"
                with open(file_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.safe_write(data)

            elif self.path.startswith("/download/"):
                raw_name = self.path[len("/download/") :].split("?")[0]
                filename = urllib.parse.unquote(raw_name)
                file_stream = store.open_download(filename, max_age_seconds)
                if file_stream is None:
                    self.send_error(404)
                    return
                with file_stream:
                    download_name = safe_upload_name(clean_display_name(filename)) or "download.bin"
                    fallback = (
                        download_name.encode("ascii", errors="replace").decode().replace('"', "_")
                    )
                    encoded = urllib.parse.quote(download_name, safe="")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(os.fstat(file_stream.fileno()).st_size))
                    self.send_header(
                        "Content-Disposition",
                        f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}",
                    )
                    self.end_headers()
                    while data := file_stream.read(CHUNK_SIZE):
                        if not self.safe_write(data):
                            break
            else:
                self.send_error(404)

        def _recent_uploads_html(self, client_ip: str) -> str:
            entries = store.list_by_ip(client_ip)
            entries = [e for e in entries if time.time() - e.time <= max_age_seconds]
            entries.sort(key=lambda e: e.time, reverse=True)
            if not entries:
                return '<tr><td colspan="4">No uploads from your IP yet.</td></tr>'
            items = []
            for entry in entries:
                display = escape(clean_display_name(entry.filename))
                url = "/download/" + urllib.parse.quote(entry.filename, safe="")
                uploaded = datetime.datetime.fromtimestamp(entry.time).strftime("%Y-%m-%d %H:%M")
                expires = datetime.datetime.fromtimestamp(entry.time + max_age_seconds).strftime(
                    "%Y-%m-%d %H:%M"
                )
                items.append(
                    f'<tr><td><a href="{url}">{display}</a></td>'
                    f"<td>{entry.size / 1024**2:.2f} MB</td>"
                    f"<td>{uploaded}</td><td>{expires}</td></tr>"
                )
            return "".join(items)

    return Handler


def start_cleanup_thread(store: DiskFileStore, interval: int, max_age_seconds: float) -> None:
    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                store.delete_expired(max_age_seconds)
            except Exception:
                logger.exception("Scheduled cleanup failed; will retry")

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


class BoundedThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, max_connections: int = 16):
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(
                    b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 1\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def run(config_path: str | None = None) -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = load_config(base_dir if config_path is None else os.path.dirname(config_path))

    upload_dir = os.path.join(base_dir, cfg.upload_dir)
    files_db_path = os.path.join(base_dir, cfg.files_db)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(os.path.dirname(files_db_path), exist_ok=True)

    store: DiskFileStore = DiskFileStore(upload_dir, files_db_path)
    limiter = RateLimiter(cfg.rate_limit_seconds)
    templates = load_templates(base_dir)
    handler_cls = make_handler(store, limiter, templates, cfg, base_dir)

    start_cleanup_thread(store, cfg.cleanup_interval_seconds, cfg.max_age_hours * 3600)

    with BoundedThreadingServer(("", cfg.port), handler_cls, cfg.max_connections) as httpd:
        print(f"Serving on port {cfg.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    run()
