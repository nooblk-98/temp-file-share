#!/bin/bash

BACKEND_URL=${BACKEND_URL:-http://localhost:54000}

if [ "$1" = "--clear" ] || [ "$1" = "-c" ]; then
    curl -s -X POST "$BACKEND_URL/clear"
    echo ""
    exit 0
fi

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    echo "       $0 --clear   (delete all files uploaded from your IP)"
    echo "Set BACKEND_URL env var for custom backend, e.g., export BACKEND_URL=https://dl.itsnooblk.com"
    exit 1
fi

temp_zip="/tmp/upload_$(date +%s).tar.gz"
echo "Zipping files (this can take a while)..."
tar --checkpoint=1000 --checkpoint-action=dot -czf "$temp_zip" "$@"
echo ""
echo "Zip created: $temp_zip"
upload_file="$temp_zip"

# upload with curl
echo "Uploading..."
url=$(curl -# -F "file=@$upload_file" $BACKEND_URL/upload)

echo "$url"

# cleanup
rm "$temp_zip"
