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

PORT = 8000

with open('config.json') as f:
    config = json.load(f)

UPLOAD_DIR = config['UPLOAD_DIR']
MAX_STORAGE_GB = config['MAX_STORAGE_GB']
MAX_AGE_SECONDS = config['MAX_AGE_HOURS'] * 3600
IP_LIMIT_GB = config['IP_LIMIT_GB']
FILES_DB = config['FILES_DB']

logging.basicConfig(filename='logs.log', level=logging.INFO, format='%(asctime)s - %(message)s')

os.makedirs(UPLOAD_DIR, exist_ok=True)

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
        for f in files:
            filepath = os.path.join(UPLOAD_DIR, f['filename'])
            if os.path.exists(filepath) and now - f['time'] > MAX_AGE_SECONDS:
                os.remove(filepath)
                updated = True
            else:
                new_files.append(f)
        if new_files:
            db[ip] = new_files
        else:
            del db[ip]
    if updated:
        save_db(db)

def get_current_used():
    return sum(os.path.getsize(os.path.join(UPLOAD_DIR, f)) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f)))

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        cleanup_old_files()
        client_ip = self.client_address[0]
        db = load_db()
        ip_files = db.get(client_ip, [])
        content_type = self.headers.get('Content-Type', '')
        data = b''
        if 'multipart/form-data' in content_type:
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type})
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
            # delete oldest files for this IP
            ip_files.sort(key=lambda x: x['time'])
            deleted = []
            while ip_files and current_ip_size + file_size > IP_LIMIT_GB * 1024**3:
                oldest = ip_files.pop(0)
                deleted.append(oldest['filename'])
                current_ip_size -= oldest['size']
                filepath = os.path.join(UPLOAD_DIR, oldest['filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
            db[client_ip] = ip_files
            save_db(db)
        current_used = get_current_used()
        if current_used + file_size > MAX_STORAGE_GB * 1024**3:
            self.send_error(413, "Not enough allocated space")
            return
        if 'multipart/form-data' in content_type:
            fileitem = form['file']
            if fileitem.filename:
                orig_name = fileitem.filename
                name, ext = os.path.splitext(orig_name)
                filename = f"{name}_{uuid.uuid4().hex}{ext}"
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
        logging.info(f'Upload: IP={client_ip}, File={filename}, Size={file_size}')
        disk_free = shutil.disk_usage(UPLOAD_DIR).free
        allocated_remaining = MAX_STORAGE_GB * 1024**3 - current_used - file_size
        ip_remaining = IP_LIMIT_GB * 1024**3 - sum(f['size'] for f in ip_files)
        expire_time = time.time() + MAX_AGE_SECONDS
        expire_str = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
        response = f'http://localhost:{PORT}/download/{filename}\nFile size: {file_size / 1024**2:.2f} MB\nExpires: {expire_str}\nDisk space left: {disk_free / 1024**3:.2f} GB\nAllocated space remaining: {allocated_remaining / 1024**3:.2f} GB\nIP limit remaining: {ip_remaining / 1024**3:.2f} GB'
        self.send_response(200)
        self.end_headers()
        self.wfile.write(response.encode())

    def do_GET(self):
        cleanup_old_files()
        if self.path.startswith('/download/'):
            filename = self.path[len('/download/'):].split('?')[0]
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                logging.info(f'Download: IP={self.client_address[0]}, File={filename}')
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

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()