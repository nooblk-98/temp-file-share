# File Upload Backend

A simple service for uploading files and folders, storing them locally, and providing download URLs.

## Features

- Automatic zipping of folders and multiple files/folders before upload
- Adjustable file expiration (default 168 hours)
- Pre-allocated storage limit (default 50 GB)
- Per-IP storage limit (default 5 GB)
- Displays file size, expiration date, and storage info after upload
- Automatic cleanup of expired files
- Automatic deletion of oldest files per IP if limit exceeded
- Logging of uploads and downloads
- Progress bars for uploads in CLI
- Multi-file/folder uploads in a single zip

## Quick Start

Download and use the upload script from your backend in one line:

**Linux/macOS:**
```bash
wget -q https://dl.itsnooblk.com/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/
# Or with curl: curl -s https://dl.itsnooblk.com/upload.sh -o upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/
```

Clear all files uploaded from your current IP:
```bash
curl -s -X POST https://dl.itsnooblk.com/clear
# Or: ./upload.sh --clear
```

Or set custom backend:
- Linux/macOS: `export BACKEND_URL=https://yourdomain.com && wget -q $BACKEND_URL/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh files`

The script will show progress and output the download URL, file size, expiration, and storage info.

## API

- `GET /`: Main page with usage guide
- `GET /upload.sh`: Download the bash upload script (Linux/macOS)
- `POST /upload`: Upload a file (multipart/form-data with 'file' field)
- `POST /clear`: Delete all files uploaded from the current IP
- `GET /download/<filename>`: Download the uploaded file

## Notes

- Folders and multiple files/folders are automatically zipped before upload.
- Files are stored with UUID-generated names to avoid conflicts.
- Expired files are cleaned up automatically on requests.
- Uploads exceeding IP limits trigger automatic deletion of oldest files for that IP.
- Logs are saved in `backend/logs.log`.
- No authentication implemented.
- If running behind Cloudflare proxy, set `TRUST_PROXY` to `true` in `backend/config.json` so per-IP limits and `/clear` use the real client IP.

## More Docs

- Development guide: `DEVELOPMENT.md`
- Contribution guide: `CONTRIBUTING.md`
