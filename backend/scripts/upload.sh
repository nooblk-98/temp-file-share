#!/bin/bash

BACKEND_URL=${BACKEND_URL:-https://dl.itsnooblk.com}

if [ "$1" = "--clear" ] || [ "$1" = "-c" ]; then
    curl -s -X POST "$BACKEND_URL/clear"
    echo ""
    exit 0
fi

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file or directory> [file2] [dir2] ..."
    echo "       $0 --clear   (delete all files uploaded from your IP)"
    echo "Set BACKEND_URL env var for custom backend, e.g., export BACKEND_URL=https://yourdomain.com"
    exit 1
fi

for input in "$@"; do
    if [ ! -e "$input" ]; then
        echo "Error: Path not found: $input"
        exit 1
    fi
done

temp_zip=""
if [ $# -eq 1 ] && [ -f "$1" ]; then
    echo "Single file detected, uploading directly: $1"
    upload_file="$1"
else
    temp_zip="/tmp/upload_$(date +%s).tar.gz"
    echo "Zipping files (this can take a while)..."
    tar --checkpoint=1000 --checkpoint-action=dot -czf "$temp_zip" "$@"
    echo ""
    echo "Zip created: $temp_zip"
    upload_file="$temp_zip"
fi

# upload with curl
echo "Uploading..."
response=$(curl -sS -F "file=@$upload_file" "$BACKEND_URL/upload")

echo "$response"

# cleanup
if [ -n "$temp_zip" ] && [ -f "$temp_zip" ]; then
    rm "$temp_zip"
fi
