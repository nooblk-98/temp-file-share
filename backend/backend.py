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

UPLOAD_SCRIPT = '''#!/bin/bash

BACKEND_URL=${BACKEND_URL:-https://dl.itsnooblk.com}

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    echo "Set BACKEND_URL env var for custom backend, e.g., export BACKEND_URL=https://yourdomain.com"
    exit 1
fi

temp_zip="/tmp/upload_$(date +%s).tar.gz"
tar -czf "$temp_zip" "$@"
upload_file="$temp_zip"

# upload with curl
url=$(curl -# -F "file=@$upload_file" $BACKEND_URL/upload)

echo "$url"

# cleanup
rm "$temp_zip"
'''

INDEX_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Upload Service</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        pre {{ background: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        .command {{ color: #2e7d32; }}
        .storage-bar {{ width: 100%; height: 20px; background: #ddd; border-radius: 10px; overflow: hidden; margin: 10px 0; }}
        .storage-used {{ height: 100%; background: #4caf50; transition: width 0.3s; }}
        .storage-text {{ text-align: center; font-size: 14px; }}
        .limits {{ background: #f9f9f9; padding: 10px; border-radius: 5px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>File Upload Service</h1>
    <p>Upload files and folders easily from your terminal.</p>
    
    <h2>Storage Usage</h2>
    <div class="storage-bar">
        <div class="storage-used" style="width: {percentage:.1f}%;"></div>
    </div>
    <div class="storage-text">{used_gb:.2f} GB used of {total_gb:.2f} GB allocated</div>
    
    <div class="limits">
        <strong>Limits:</strong> Files expire after {max_age_hours} hours. Per-IP limit: {ip_limit_gb:.2f} GB.
    </div>
    
    <h2>Quick Start</h2>
    <p>Download the upload script and use it:</p>
    <pre><code class="command">wget -q https://dl.itsnooblk.com/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/</code></pre>
    <p>Or with curl:</p>
    <pre><code class="command">curl -s https://dl.itsnooblk.com/upload.sh -o upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/</code></pre>
    
    <h2>Features</h2>
    <ul>
        <li>Automatic zipping of folders and multiple files</li>
        <li>File expiration after {max_age_hours} hours</li>
        <li>Per-IP storage limits ({ip_limit_gb:.2f} GB)</li>
        <li>Progress bars for uploads</li>
        <li>Direct download links</li>
    </ul>
    
    <h2>Direct Upload</h2>
    <p>Upload single file:</p>
    <pre><code>curl -F "file=@file.zip" https://dl.itsnooblk.com/upload</code></pre>
    <p>Upload folder (zip first):</p>
    <pre><code>tar -czf archive.tar.gz folder && curl -F "file=@archive.tar.gz" https://dl.itsnooblk.com/upload</code></pre>
    
    <h2>Download</h2>
    <p>Use wget or curl to download files:</p>
    <pre><code>wget https://dl.itsnooblk.com/download/filename</code></pre>
    
    <footer style="margin-top: 40px; text-align: center; font-size: 12px; color: #666;">
        Created by <a href="https://github.com/nooblk-98" target="_blank">nooblk-98</a> | Powered by OpenCode
    </footer>
</body>
</html>
'''

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
        logging.info(f'Upload: IP={client_ip}, File={filename}, Size={file_size}')
        disk_free = shutil.disk_usage(UPLOAD_DIR).free
        allocated_remaining = MAX_STORAGE_GB * 1024**3 - current_used - file_size
        ip_remaining = IP_LIMIT_GB * 1024**3 - sum(f['size'] for f in ip_files)
        expire_time = time.time() + MAX_AGE_SECONDS
        expire_str = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
        response = f'https://dl.itsnooblk.com/download/{filename}\nFile size: {file_size / 1024**2:.2f} MB\nExpires: {expire_str}\nDisk space left: {disk_free / 1024**3:.2f} GB\nAllocated space remaining: {allocated_remaining / 1024**3:.2f} GB\nIP limit remaining: {ip_remaining / 1024**3:.2f} GB'
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
            html = INDEX_HTML.format(
                used_gb=used_gb, 
                total_gb=total_gb, 
                percentage=percentage,
                max_age_hours=config['MAX_AGE_HOURS'],
                ip_limit_gb=config['IP_LIMIT_GB']
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
        elif self.path.startswith('/download/'):
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