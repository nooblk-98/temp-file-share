# File Upload Backend

A simple backend service for uploading files and folders, storing them locally, and providing download URLs.

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

## Quick Start

Download and use the upload script from your backend in one line:

**Linux/macOS:**
```bash
wget -q https://dl.itsnooblk.com/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/
# Or with curl: curl -s https://dl.itsnooblk.com/upload.sh -o upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/
```

**Windows (CMD or PowerShell):**
```cmd
powershell -Command "Invoke-WebRequest -Uri https://dl.itsnooblk.com/upload.ps1 -OutFile upload.ps1; .\upload.ps1 filename.zip folder/"
```

Or set custom backend: `export BACKEND_URL=https://yourdomain.com && wget -q $BACKEND_URL/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh files`


## Prerequisites

- Docker and Docker Compose installed (for local deployment)
- Bash shell (for upload.sh)
- For public deployment, a server with domain like dl.itsnooblk.com

## Deployment

For local: Use Docker Compose as below.

For public: Deploy the backend to a server (e.g., using Docker on VPS), point domain to it, and set BACKEND_URL.

## Running the Application

1. Start the backend server:
   ```bash
   docker-compose up --build
   ```

2. Upload using the script:
   ```bash
   ./upload.sh file1.txt folder1
   ```

Or set custom backend: `export BACKEND_URL=https://dl.itsnooblk.com && ./upload.sh file1.txt`

The script will show progress and output download URL, file size, expiration, and storage info.

## API

## API

- `GET /`: Main page with usage guide
- `GET /upload.sh`: Download the bash upload script (Linux/macOS)
- `GET /upload.ps1`: Download the PowerShell upload script (Windows)
- `POST /upload`: Upload a file (multipart/form-data with 'file' field)
- `GET /download/<filename>`: Download the uploaded file

## Notes

- Folders and multiple files/folders are automatically zipped before upload.
- Files are stored with UUID-generated names to avoid conflicts.
- Expired files are cleaned up automatically on requests.
- Uploads exceeding IP limits trigger automatic deletion of oldest files for that IP.
- Logs are saved in `backend/logs.log`.
- No authentication implemented.

## Structure

- `backend/`: Contains the Python backend server
  - `backend.py`: The main server script
  - `index.html`: Template for the main page
  - `config.json`: Configuration file for limits
  - `Dockerfile`: Docker image definition
  - `uploads/`: Directory where uploaded files are stored (created at runtime)
  - `files_db.json`: JSON database tracking files per IP
  - `logs.log`: Log file for uploads and downloads
- `upload.sh`: Bash script to upload files or folders
- `docker-compose.yml`: Docker Compose configuration to run the backend

