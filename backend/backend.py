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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, 'config.json')) as f:
    config = json.load(f)

UPLOAD_DIR = config['UPLOAD_DIR']
MAX_STORAGE_GB = config['MAX_STORAGE_GB']
MAX_AGE_SECONDS = config['MAX_AGE_HOURS'] * 3600
IP_LIMIT_GB = config['IP_LIMIT_GB']
FILES_DB = config['FILES_DB']

UPLOAD_SCRIPT = '''#!/bin/bash

BACKEND_URL=${BACKEND_URL:-https://dl.itsnooblk.com}
TOKEN_FILE="${UPLOAD_TOKEN_FILE:-$HOME/.upload_token}"
UPLOAD_TOKEN=${UPLOAD_TOKEN:-}

if [ -z "$UPLOAD_TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
    UPLOAD_TOKEN=$(cat "$TOKEN_FILE")
fi

if [ "$1" = "--token" ]; then
    if [ -z "$UPLOAD_TOKEN" ]; then
        echo "No upload token found."
        exit 1
    fi
    echo "$UPLOAD_TOKEN"
    exit 0
fi

if [ "$1" = "--check" ]; then
    if [ -z "$UPLOAD_TOKEN" ]; then
        echo "No upload token found. Set UPLOAD_TOKEN or upload once to create one."
        exit 1
    fi
    curl -s -H "X-Upload-Token: $UPLOAD_TOKEN" "$BACKEND_URL/token"
    echo ""
    exit 0
fi

if [ "$1" = "--clear" ] || [ "$1" = "-c" ]; then
    if [ -z "$UPLOAD_TOKEN" ]; then
        echo "No upload token found. Set UPLOAD_TOKEN or upload once to create one."
        exit 1
    fi
    curl -s -X POST -H "X-Upload-Token: $UPLOAD_TOKEN" "$BACKEND_URL/clear"
    echo ""
    exit 0
fi

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    echo "       $0 --clear   (delete all files uploaded with your token)"
    echo "       $0 --check   (show token usage)"
    echo "       $0 --token   (print your token)"
    echo "Set BACKEND_URL env var for custom backend, e.g., export BACKEND_URL=https://yourdomain.com"
    exit 1
fi

temp_zip="/tmp/upload_$(date +%s).tar.gz"
tar -czf "$temp_zip" "$@"
upload_file="$temp_zip"

# upload with curl
if [ -n "$UPLOAD_TOKEN" ]; then
    response=$(curl -# -H "X-Upload-Token: $UPLOAD_TOKEN" -F "file=@$upload_file" "$BACKEND_URL/upload")
else
    response=$(curl -# -F "file=@$upload_file" "$BACKEND_URL/upload")
fi

echo "$response"
token=$(echo "$response" | sed -n 's/^Token: //p')
if [ -n "$token" ]; then
    echo "$token" > "$TOKEN_FILE"
fi

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
    
    <h2>💾 Storage Usage</h2>
    <div class="storage-bar">
        <div class="storage-used" style="width: {percentage:.1f}%; background: linear-gradient(to right, #4caf50, #ff9800, #f44336);"></div>
    </div>
    <div class="storage-text">{used_gb:.2f} GB used of {total_gb:.2f} GB allocated ({percentage:.1f}%)</div>
    
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
    
    <footer style="margin-top: 40px; text-align: center; font-size: 12px; color: #666;">
        Created by <a href="https://github.com/nooblk-98" target="_blank">nooblk-98</a> | Powered by python
    </footer>
</body>
</html>
'''

with open(os.path.join(BASE_DIR, 'index.html')) as f:
    INDEX_TEMPLATE = f.read()

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

def get_token_from_request(handler):
    header_token = handler.headers.get('X-Upload-Token')
    if header_token:
        return header_token.strip()
    if '?' in handler.path:
        query = handler.path.split('?', 1)[1]
        for part in query.split('&'):
            if part.startswith('token='):
                return part.split('=', 1)[1].strip()
    return None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        cleanup_old_files()
        token = get_token_from_request(self)
        if self.path == '/token':
            if not token:
                self.send_error(400, "Missing upload token")
                return
            db = load_db()
            token_files = db.get(token, [])
            used_bytes = sum(f['size'] for f in token_files)
            used_gb = used_bytes / 1024**3
            remaining_gb = max(IP_LIMIT_GB - used_gb, 0)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                f'Token: {token}\nFiles: {len(token_files)}\nUsed: {used_gb:.2f} GB\nRemaining: {remaining_gb:.2f} GB'.encode()
            )
            return
        if self.path == '/clear':
            if not token:
                self.send_error(400, "Missing upload token")
                return
            db = load_db()
            token_files = db.get(token, [])
            freed_bytes = 0
            for entry in token_files:
                filepath = os.path.join(UPLOAD_DIR, entry['filename'])
                if os.path.exists(filepath):
                    try:
                        size = os.path.getsize(filepath)
                    except OSError:
                        size = 0
                    os.remove(filepath)
                    freed_bytes += size
            if token in db:
                del db[token]
                save_db(db)
            logging.info(f'Clear: Token={token}, Freed={freed_bytes}')
            self.send_response(200)
            self.end_headers()
            freed_mb = freed_bytes / 1024**2
            self.wfile.write(f'Cleared files for token {token}. Freed {freed_mb:.2f} MB'.encode())
            return
        db = load_db()
        if not token:
            token = uuid.uuid4().hex
        token_files = db.get(token, [])
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
        current_token_size = sum(f['size'] for f in token_files)
        if current_token_size + file_size > IP_LIMIT_GB * 1024**3:
            # delete oldest files for this token
            token_files.sort(key=lambda x: x['time'])
            while token_files and current_token_size + file_size > IP_LIMIT_GB * 1024**3:
                oldest = token_files.pop(0)
                current_token_size -= oldest['size']
                filepath = os.path.join(UPLOAD_DIR, oldest['filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
            db[token] = token_files
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
        token_files.append({'filename': filename, 'size': file_size, 'time': time.time()})
        db[token] = token_files
        save_db(db)
        logging.info(f'Upload: Token={token}, File={filename}, Size={file_size}')
        disk_free = shutil.disk_usage(UPLOAD_DIR).free
        allocated_remaining = MAX_STORAGE_GB * 1024**3 - current_used - file_size
        ip_remaining = IP_LIMIT_GB * 1024**3 - sum(f['size'] for f in token_files)
        expire_time = time.time() + MAX_AGE_SECONDS
        expire_str = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
        response = f'https://dl.itsnooblk.com/download/{filename}\nToken: {token}\nFile size: {file_size / 1024**2:.2f} MB\nExpires: {expire_str}\nDisk space left: {disk_free / 1024**3:.2f} GB\nAllocated space remaining: {allocated_remaining / 1024**3:.2f} GB\nIP limit remaining: {ip_remaining / 1024**3:.2f} GB'
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
            html = INDEX_TEMPLATE.format(
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
        elif self.path.startswith('/token'):
            token = get_token_from_request(self)
            if not token:
                self.send_error(400, "Missing upload token")
                return
            db = load_db()
            token_files = db.get(token, [])
            used_bytes = sum(f['size'] for f in token_files)
            used_gb = used_bytes / 1024**3
            remaining_gb = max(IP_LIMIT_GB - used_gb, 0)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                f'Token: {token}\nFiles: {len(token_files)}\nUsed: {used_gb:.2f} GB\nRemaining: {remaining_gb:.2f} GB'.encode()
            )
        elif self.path.startswith('/download/'):
            filename = self.path[len('/download/'):].split('?')[0]
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                logging.info(f'Download: File={filename}')
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
