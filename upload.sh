#!/bin/bash

BACKEND_URL=${BACKEND_URL:-http://localhost:8000}

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    echo "Set BACKEND_URL env var for custom backend, e.g., export BACKEND_URL=https://dl.itsnooblk.com"
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