#!/usr/bin/env python3

import http.server
import socketserver
import os
import uuid
import cgi
import time
import shutil
import json
import datetime
import logging
import threading
from html import escape
import ipaddress
import urllib.request
import urllib.error

PORT = 54000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(BASE_DIR, 'config.json')) as f:
        return json.load(f)


config = load_config()

UPLOAD_DIR = os.path.join(BASE_DIR, config['UPLOAD_DIR'])
MAX_STORAGE_GB = config['MAX_STORAGE_GB']
MAX_AGE_SECONDS = config['MAX_AGE_HOURS'] * 3600
IP_LIMIT_GB = config['IP_LIMIT_GB']
FILES_DB = os.path.join(BASE_DIR, config['FILES_DB'])
RATE_LIMIT_SECONDS = config.get('RATE_LIMIT_SECONDS', 0)
CLEANUP_INTERVAL_SECONDS = config.get('CLEANUP_INTERVAL_SECONDS', 300)

TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates', 'index.html')
UPLOAD_SCRIPT_PATH = os.path.join(BASE_DIR, 'scripts', 'upload.sh')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

with open(TEMPLATE_PATH) as f:
    INDEX_TEMPLATE = f.read()

with open(UPLOAD_SCRIPT_PATH) as f:
    UPLOAD_SCRIPT = f.read()


def load_db():
    if os.path.exists(FILES_DB):
        with open(FILES_DB) as f:
            return json.load(f)
    return {}


def save_db(db):
    with open(FILES_DB, 'w') as f:
        json.dump(db, f)


def cleanup_old_files():
    db = load_db()
    now = time.time()
    updated = False
    for ip, files in list(db.items()):
        new_files = []
        for entry in files:
            filepath = os.path.join(UPLOAD_DIR, entry['filename'])
            if os.path.exists(filepath) and now - entry['time'] > MAX_AGE_SECONDS:
                os.remove(filepath)
                updated = True
            else:
                new_files.append(entry)
        if new_files:
            db[ip] = new_files
        else:
            del db[ip]
    if updated:
        save_db(db)


def get_current_used():
    return sum(
        os.path.getsize(os.path.join(UPLOAD_DIR, f))
        for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    )

def get_client_ip(handler):
    x_real_ip = handler.headers.get('X-Real-IP')
    if x_real_ip:
        return x_real_ip.strip()
    xff = handler.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return handler.client_address[0]

def is_private_ip(ip_value):
    try:
        return ipaddress.ip_address(ip_value).is_private
    except ValueError:
        return False

def get_recent_uploads(limit=None):
    db = load_db()
    all_files = []
    for ip, files in db.items():
        for entry in files:
            entry_copy = dict(entry)
            entry_copy['ip'] = ip
            all_files.append(entry_copy)
    all_files.sort(key=lambda x: x.get('time', 0), reverse=True)
    if limit is not None:
        all_files = all_files[:limit]
    if not all_files:
        return '<tr><td colspan="5">No uploads yet</td></tr>'
    items = []
    for entry in all_files:
        filename = entry.get('filename', 'unknown')
        display_name = clean_display_name(filename)
        size_mb = entry.get('size', 0) / 1024**2
        ts = entry.get('time', 0)
        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        exp_ts = entry.get('time', 0) + MAX_AGE_SECONDS
        exp_str = datetime.datetime.fromtimestamp(exp_ts).strftime('%Y-%m-%d %H:%M:%S')
        ip_value = entry.get('ip', 'unknown')
        country_html = get_country_display(ip_value)
        items.append(
            '<tr>'
            f'<td>{escape(display_name)}</td>'
            f'<td>{size_mb:.2f} MB</td>'
            f'<td>{ts_str}</td>'
            f'<td>{exp_str}</td>'
            f'<td>{escape(ip_value)}</td>'
            f'<td>{country_html}</td>'
            '</tr>'
        )
    return ''.join(items)


def clean_display_name(filename):
    if len(filename) > 33 and filename[32] == '_' and all(c in '0123456789abcdef' for c in filename[:32]):
        return filename[33:]
    return filename


_geo_cache = {}


def get_country_display(ip_value):
    if not ip_value:
        return ''
    if is_private_ip(ip_value):
        return 'LAN'
    cached = _geo_cache.get(ip_value)
    if cached is not None:
        return cached
    code = lookup_country_code(ip_value)
    if not code:
        _geo_cache[ip_value] = ''
        return ''
    flag = country_code_to_flag(code)
    text = f'{code.upper()} {flag}' if flag else f'{code.upper()}'
    _geo_cache[ip_value] = text
    return text


def lookup_country_code(ip_value):
    url = f'http://ip-api.com/json/{ip_value}?fields=status,countryCode'
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('status') == 'success':
            return data.get('countryCode')
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None
    return None


def country_code_to_flag(code):
    if not code or len(code) != 2:
        return ''
    code_lower = code.lower()
    return f'<img class="flag-img" src="https://flagcdn.com/w20/{code_lower}.png" alt="{code.upper()} flag">'


def start_cleanup_thread():
    def _loop():
        while True:
            time.sleep(CLEANUP_INTERVAL_SECONDS)
            cleanup_old_files()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


last_upload_time = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        cleanup_old_files()
        client_ip = get_client_ip(self)

        if self.path not in ('/upload', '/clear'):
            self.send_error(404)
            return

        if RATE_LIMIT_SECONDS and self.path == '/upload':
            last_time = last_upload_time.get(client_ip, 0)
            if time.time() - last_time < RATE_LIMIT_SECONDS:
                self.send_error(429, f"Rate limit: wait {RATE_LIMIT_SECONDS} seconds between uploads.")
                return

        if self.path == '/clear':
            db = load_db()
            ip_files = db.get(client_ip, [])
            freed_bytes = 0
            for entry in ip_files:
                filepath = os.path.join(UPLOAD_DIR, entry['filename'])
                if os.path.exists(filepath):
                    try:
                        size = os.path.getsize(filepath)
                    except OSError:
                        size = 0
                    os.remove(filepath)
                    freed_bytes += size
            if client_ip in db:
                del db[client_ip]
                save_db(db)
            logging.info(f'Clear: IP={client_ip}, Freed={freed_bytes}')
            self.send_response(200)
            self.end_headers()
            freed_mb = freed_bytes / 1024**2
            self.wfile.write(f'Cleared files for IP {client_ip}. Freed {freed_mb:.2f} MB'.encode())
            return

        db = load_db()
        ip_files = db.get(client_ip, [])
        content_type = self.headers.get('Content-Type', '')
        data = b''
        if 'multipart/form-data' in content_type:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type},
            )
            if 'file' in form:
                fileitem = form['file']
                data = fileitem.file.read()
            else:
                self.send_error(400)
                return
        else:
            content_length = int(self.headers['Content-Length'])
            data = self.rfile.read(content_length)

        file_size = len(data)
        current_ip_size = sum(f['size'] for f in ip_files)
        if current_ip_size + file_size > IP_LIMIT_GB * 1024**3:
            self.send_error(413, 'IP limit exceeded. Run ./upload.sh --clear and retry.')
            return

        current_used = get_current_used()
        if current_used + file_size > MAX_STORAGE_GB * 1024**3:
            self.send_error(413, 'Not enough allocated space')
            return

        if 'multipart/form-data' in content_type:
            fileitem = form['file']
            if fileitem.filename:
                orig_name = fileitem.filename
                filename = f"{uuid.uuid4().hex}_{orig_name}"
            else:
                filename = str(uuid.uuid4()) + '.bin'
        else:
            filename = str(uuid.uuid4()) + '.bin'

        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(data)

        ip_files.append({'filename': filename, 'size': file_size, 'time': time.time()})
        db[client_ip] = ip_files
        save_db(db)
        last_upload_time[client_ip] = time.time()
        logging.info(f'Upload: IP={client_ip}, File={filename}, Size={file_size}')

        disk_free = shutil.disk_usage(UPLOAD_DIR).free
        allocated_remaining = MAX_STORAGE_GB * 1024**3 - current_used - file_size
        ip_remaining = IP_LIMIT_GB * 1024**3 - sum(f['size'] for f in ip_files)
        expire_time = time.time() + MAX_AGE_SECONDS
        expire_str = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')

        response = (
            f'https://dl.itsnooblk.com/download/{filename}\n'
            f'Your IP: {client_ip}\n'
            f'File size: {file_size / 1024**2:.2f} MB\n'
            f'Expires: {expire_str}\n'
            f'Disk space left: {disk_free / 1024**3:.2f} GB\n'
            f'Allocated space remaining: {allocated_remaining / 1024**3:.2f} GB\n'
            f'IP limit remaining: {ip_remaining / 1024**3:.2f} GB'
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(response.encode())

    def do_GET(self):
        cleanup_old_files()
        if self.path in ('/', '/index.html'):
            used_bytes = get_current_used()
            used_gb = used_bytes / 1024**3
            total_gb = MAX_STORAGE_GB
            percentage = (used_gb / total_gb) * 100 if total_gb > 0 else 0
            recent_uploads_html = get_recent_uploads()
            html = INDEX_TEMPLATE.format(
                used_gb=used_gb,
                total_gb=total_gb,
                percentage=percentage,
                max_age_hours=config['MAX_AGE_HOURS'],
                ip_limit_gb=config['IP_LIMIT_GB'],
                recent_uploads_html=recent_uploads_html,
            )
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == '/upload.sh':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Disposition', 'attachment; filename="upload.sh"')
            self.end_headers()
            self.wfile.write(UPLOAD_SCRIPT.encode())
        elif self.path.startswith('/static/'):
            rel_path = self.path[len('/static/') :]
            if rel_path not in ('styles.css', 'app.js'):
                self.send_error(404)
                return
            file_path = os.path.join(STATIC_DIR, rel_path)
            if not os.path.exists(file_path):
                self.send_error(404)
                return
            content_type = 'text/css' if rel_path.endswith('.css') else 'application/javascript'
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith('/download/'):
            filename = self.path[len('/download/') :].split('?')[0]
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                logging.info(f'Download: IP={get_client_ip(self)}, File={filename}')
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        else:
            self.send_error(404)


def run():
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("", PORT), Handler) as httpd:
        start_cleanup_thread()
        print(f"Serving on port {PORT}")
        httpd.serve_forever()


if __name__ == '__main__':
    run()
