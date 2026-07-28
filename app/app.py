from __future__ import annotations

import datetime
import http.server
import ipaddress
import logging
import os
import shutil
import socketserver
import threading
import time
import urllib.parse
import uuid
from html import escape

from _types import IPAddress, Config
from config import load_config
from filestore import FileStore, DiskFileStore
from georesolver import GeoResolver, NullGeoResolver, HttpGeoResolver
from ratelimiter import RateLimiter

logger = logging.getLogger("temp-file-share")
PORT = 54000


def get_client_ip(handler: http.server.BaseHTTPRequestHandler) -> IPAddress:
    x_real_ip = handler.headers.get("X-Real-IP")
    if x_real_ip:
        return IPAddress(x_real_ip.strip())
    xff = handler.headers.get("X-Forwarded-For")
    if xff:
        return IPAddress(xff.split(",")[0].strip())
    return IPAddress(handler.client_address[0])


def is_private_ip(ip_value: str) -> bool:
    try:
        return ipaddress.ip_address(ip_value).is_private
    except ValueError:
        return False


def clean_display_name(filename: str) -> str:
    if (
        len(filename) > 33
        and filename[32] == "_"
        and all(c in "0123456789abcdef" for c in filename[:32])
    ):
        return filename[33:]
    return filename


def country_code_to_flag(code: str) -> str:
    if not code or len(code) != 2:
        return ""
    return (
        f'<img class="flag-img" src="https://flagcdn.com/w20/{code.lower()}.png"'
        f' alt="{code.upper()} flag">'
    )


def get_public_base_url(handler: http.server.BaseHTTPRequestHandler, config: Config) -> str:
    configured = config.public_base_url.rstrip("/")
    if configured:
        return configured
    forwarded_proto = handler.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
    host = handler.headers.get("Host", f"localhost:{PORT}")
    return f"{forwarded_proto}://{host}"


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
    store: FileStore,
    geo: GeoResolver,
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
        def safe_write(self, data: bytes) -> bool:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        def do_POST(self) -> None:
            store.delete_expired(max_age_seconds)
            client_ip = get_client_ip(self)

            if self.path not in ("/upload", "/clear"):
                self.send_error(404)
                return

            if self.path == "/upload" and not limiter.allow(client_ip):
                self.send_error(
                    429, f"Rate limit: wait {config.rate_limit_seconds} seconds between uploads."
                )
                return

            if self.path == "/clear":
                freed = store.delete_by_ip(client_ip)
                logger.info("Clear: IP=%s, Freed files=%d", client_ip, freed)
                self.send_response(200)
                self.end_headers()
                self.safe_write(f"Cleared files for IP {client_ip}.".encode())
                return

            content_type = self.headers.get("Content-Type", "")
            data: bytes = b""
            orig_name: str | None = None

            if "multipart/form-data" in content_type:
                import cgi
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
                )
                if "file" not in form:
                    self.send_error(400)
                    return
                fileitem = form["file"]
                data = fileitem.file.read()
                orig_name = fileitem.filename
            else:
                content_length = int(self.headers["Content-Length"])
                data = self.rfile.read(content_length)

            file_size = len(data)
            ip_used = store.used_bytes_by_ip(client_ip)
            if ip_used + file_size > ip_limit_bytes:
                self.send_error(413, "IP limit exceeded. Run ./upload.sh --clear and retry.")
                return
            total_used = store.used_bytes()
            if total_used + file_size > max_storage_bytes:
                self.send_error(413, "Not enough allocated space")
                return

            if orig_name:
                filename = f"{uuid.uuid4().hex}_{orig_name}"
            else:
                filename = str(uuid.uuid4()) + ".bin"

            store.store(client_ip, filename, data)
            logger.info("Upload: IP=%s, File=%s, Size=%d", client_ip, filename, file_size)

            disk_free = shutil.disk_usage(upload_dir).free
            allocated_remaining = max_storage_bytes - store.used_bytes()
            ip_remaining = ip_limit_bytes - store.used_bytes_by_ip(client_ip)
            expire_time = time.time() + max_age_seconds
            expire_str = datetime.datetime.fromtimestamp(expire_time).strftime("%Y-%m-%d %H:%M:%S")

            base_url = config.public_base_url.rstrip("/")
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
            store.delete_expired(max_age_seconds)

            if self.path in ("/", "/index.html"):
                used_bytes = store.used_bytes()
                used_gb = used_bytes / 1024**3
                percentage = (used_gb / config.max_storage_gb) * 100 if config.max_storage_gb > 0 else 0
                client_ip = get_client_ip(self)
                ip_used_gb = store.used_bytes_by_ip(client_ip) / 1024**3
                ip_percentage = (ip_used_gb / config.ip_limit_gb) * 100 if config.ip_limit_gb > 0 else 0
                recent_html = self._recent_uploads_html(client_ip)
                base_url = get_public_base_url(self, config)
                html = templates["index"].format(
                    used_gb=used_gb,
                    total_gb=config.max_storage_gb,
                    percentage=percentage,
                    ip_used_gb=ip_used_gb,
                    ip_percentage=ip_percentage,
                    max_age_hours=config.max_age_hours,
                    ip_limit_gb=config.ip_limit_gb,
                    public_base_url=base_url,
                    base_url=base_url,
                    recent_uploads_html=recent_html,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.safe_write(html.encode())

            elif self.path in ("/uploads", "/uploads.html"):
                client_ip = get_client_ip(self)
                recent_html = self._recent_uploads_html()
                base_url = get_public_base_url(self, config)
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
                lastmod = datetime.datetime.utcnow().date().isoformat()
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
                self.safe_write(templates["upload_script"].encode())

            elif self.path.startswith("/static/"):
                rel_path = self.path[len("/static/"):]
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
                raw_name = self.path[len("/download/"):].split("?")[0]
                filename = urllib.parse.unquote(raw_name)
                file_data = store.retrieve(filename)
                if file_data is not None:
                    logger.info("Download: IP=%s, File=%s", get_client_ip(self), filename)
                    download_name = clean_display_name(filename)
                    download_name_safe = download_name.replace('"', "")
                    download_name_encoded = urllib.parse.quote(download_name_safe, safe="")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{download_name_safe}"; filename*=UTF-8\'\'{download_name_encoded}',
                    )
                    self.end_headers()
                    self.safe_write(file_data)
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        def _recent_uploads_html(self, client_ip: str | None = None) -> str:
            all_entries = store.entries()
            rows: list[dict[str, object]] = []
            for ip, files in all_entries.items():
                for entry in files:
                    rows.append({
                        "filename": entry.filename,
                        "size": entry.size,
                        "time": entry.time,
                        "ip": ip,
                    })
            rows.sort(key=lambda x: float(x.get("time", 0)), reverse=True)
            if not rows:
                return '<tr><td colspan="5">No uploads yet</td></tr>'
            items: list[str] = []
            for entry in rows:
                fname = str(entry.get("filename", "unknown"))
                display_name = clean_display_name(fname)
                size_mb = int(entry.get("size", 0)) / 1024**2
                ts = float(entry.get("time", 0))
                ts_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                exp_ts = ts + max_age_seconds
                exp_str = datetime.datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M:%S")
                ip_value = str(entry.get("ip", "unknown"))

                country_code = geo.resolve(ip_value) if geo else None
                country_html = ""
                if country_code:
                    flag = country_code_to_flag(country_code)
                    country_html = f"{country_code.upper()} {flag}" if flag else country_code.upper()
                elif is_private_ip(ip_value):
                    country_html = "LAN"

                items.append(
                    "<tr>"
                    f'<td>{escape(display_name)}</td>'
                    f"<td>{size_mb:.2f} MB</td>"
                    f"<td>{ts_str}</td>"
                    f"<td>{exp_str}</td>"
                    f"<td>{escape(ip_value)}</td>"
                    f"<td>{country_html}</td>"
                    "</tr>"
                )
            return "".join(items)

    return Handler


def start_cleanup_thread(store: FileStore, interval: int, max_age_seconds: float) -> None:
    def _loop() -> None:
        while True:
            time.sleep(interval)
            store.delete_expired(max_age_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def run(config_path: str | None = None) -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = load_config(base_dir if config_path is None else os.path.dirname(config_path))

    upload_dir = os.path.join(base_dir, cfg.upload_dir)
    files_db_path = os.path.join(base_dir, cfg.files_db)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(os.path.dirname(files_db_path), exist_ok=True)

    store: FileStore = DiskFileStore(upload_dir, files_db_path)
    geo: GeoResolver = HttpGeoResolver() if cfg.geo_ip_enabled else NullGeoResolver()
    limiter = RateLimiter(cfg.rate_limit_seconds)
    templates = load_templates(base_dir)
    handler_cls = make_handler(store, geo, limiter, templates, cfg, base_dir)

    start_cleanup_thread(store, cfg.cleanup_interval_seconds, cfg.max_age_hours * 3600)

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("", PORT), handler_cls) as httpd:
        print(f"Serving on port {PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    run()
