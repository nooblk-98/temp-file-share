# File Upload Backend

Upload files and folders from your terminal and get a download link.

## Features

- Upload files and folders (auto-zipped)
- Download link returned after upload
- Files expire automatically
- Per-IP storage limits

## Quick Start (Linux/macOS)

One line install + upload:
```bash
wget -q https://dl.itsnooblk.com/upload.sh -O upload.sh && chmod +x upload.sh && ./upload.sh filename.zip folder/
```

## Clear Your Files (Same IP)

Delete everything you uploaded from your current IP (one line):
```bash
curl -s https://dl.itsnooblk.com/upload.sh -o upload.sh && chmod +x upload.sh && ./upload.sh --clear
```

## Custom Backend

```bash
export BACKEND_URL=https://yourdomain.com
wget -q $BACKEND_URL/upload.sh -O upload.sh
chmod +x upload.sh
./upload.sh files
```

## API

- `GET /`: Main page with usage guide
- `GET /upload.sh`: Download the bash upload script (Linux/macOS)
- `POST /upload`: Upload a file (multipart/form-data with 'file' field)
- `POST /clear`: Delete all files uploaded from the current IP
- `GET /download/<filename>`: Download the uploaded file

## Notes

- Folders and multiple files are auto-zipped before upload.
- Files are stored with UUID names.
- Expired files are cleaned up automatically.
- Limits apply per IP.
- If you hit the IP limit, run `./upload.sh --clear` and try again.

## More Docs

- Development guide: `DEVELOPMENT.md`
- Contribution guide: `CONTRIBUTING.md`
