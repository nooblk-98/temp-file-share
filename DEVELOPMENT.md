# Development Guide

This document covers local development and deployment for the File Upload Backend.

## Prerequisites

- Docker and Docker Compose
- Bash shell (for `upload.sh`)

## Local Development (Docker Compose)

1. Build and start:
   ```bash
   docker-compose up --build
   ```
2. Open the service in your browser:
   ```
   http://localhost:8000
   ```
3. Upload using the script:
   ```bash
   ./upload.sh file1.txt folder1
   ```

## Configuration

The backend reads `backend/config.json` on startup.

Key settings:
- `UPLOAD_DIR`: directory for uploaded files
- `MAX_STORAGE_GB`: allocated storage limit
- `MAX_AGE_HOURS`: file expiration time
- `IP_LIMIT_GB`: per-IP storage limit
- `FILES_DB`: JSON database path
Note: per-uploader limits are keyed by upload token (not IP).

## File Storage

- Uploaded files are stored under `backend/uploads/` (created at runtime).
- File metadata is tracked in `backend/files_db.json`.
- Logs are written to `backend/logs.log`.

## API (for testing)

- `GET /`: Main page
- `GET /upload.sh`: Download upload script
- `POST /upload`: Upload a file (multipart/form-data with `file` field)
- `GET /token`: Show token usage (`X-Upload-Token`)
- `POST /clear`: Delete all files uploaded with your token (`X-Upload-Token`)
- `GET /download/<filename>`: Download uploaded file

## Troubleshooting

- If you change `backend/index.html` or `backend/backend.py`, rebuild the image.
- If storage limits seem wrong, verify `backend/config.json` is mounted/copied.
