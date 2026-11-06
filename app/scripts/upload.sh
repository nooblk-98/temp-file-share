#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL=${BACKEND_URL:-https://fs.app.itsnooblk.com}
BACKEND_URL=${BACKEND_URL%/}

if [[ ${1:-} == --clear || ${1:-} == -c ]]; then
    curl -fsS -X POST "$BACKEND_URL/clear"
    printf '\n'
    exit 0
fi
if [[ $# -eq 0 ]]; then
    printf 'Usage: %s <file or directory> [file2] [dir2] ...\n       %s --clear\nSet BACKEND_URL for another server.\n' "$0" "$0" >&2
    exit 1
fi
for input in "$@"; do
    if [[ ! -e $input ]]; then
        printf 'Error: Path not found: %s\n' "$input" >&2
        exit 1
    fi
done

temp_dir=''
cleanup() {
    if [[ -n $temp_dir ]]; then
        rm -f -- "$temp_dir/upload.tar.gz"
        rmdir -- "$temp_dir"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ $# -eq 1 && -f $1 ]]; then
    upload_file=$1
else
    temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/temp-file-share.XXXXXXXX")
    upload_file=$temp_dir/upload.tar.gz
    printf 'Creating archive...\n' >&2
    # BSD tar (macOS) and GNU tar both support this invocation.
    tar -czf "$upload_file" -- "$@"
fi
printf 'Uploading...\n' >&2
curl -fsS -F "file=@$upload_file" "$BACKEND_URL/upload"
printf '\n'
