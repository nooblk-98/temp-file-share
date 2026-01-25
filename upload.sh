#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    exit 1
fi

temp_zip="/tmp/upload_$(date +%s).tar.gz"
tar -czf "$temp_zip" "$@"
upload_file="$temp_zip"

# upload with curl
url=$(curl -# -F "file=@$upload_file" http://localhost:8000/upload)

echo "$url"

# cleanup
rm "$temp_zip"