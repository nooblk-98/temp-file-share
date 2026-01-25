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

## Running the Application

1. Start the backend server:
   ```bash
   docker-compose up --build
   ```

2. In another terminal, upload files or folders:
   ```bash
   ./upload.sh file1.txt folder1 file2.jpg
   ```

The script will show progress and output download URL, file size, expiration, and storage info.

## API

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
  - `config.json`: Configuration file for limits
  - `Dockerfile`: Docker image definition
  - `uploads/`: Directory where uploaded files are stored (created at runtime)
  - `files_db.json`: JSON database tracking files per IP
  - `logs.log`: Log file for uploads and downloads
- `upload.sh`: Bash script to upload files or folders
- `docker-compose.yml`: Docker Compose configuration to run the backend

