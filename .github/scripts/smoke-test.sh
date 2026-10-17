#!/usr/bin/env bash
# Container smoke test: start the image, wait for healthy, upload a file and
# download it back. Runs the container the way production should: non-root,
# read-only root fs, all capabilities dropped.
#
# Usage: smoke-test.sh <image> [host-port]
set -euo pipefail

IMAGE="${1:?usage: smoke-test.sh <image> [host-port]}"
PORT="${2:-34101}"
NAME="tfs-smoke-$$"
TMPVOL="tfs-smoke-tmp-$$"
WORK="$(mktemp -d)"
# Git Bash on Windows needs a native path for docker -v (a no-op on Linux).
MOUNT="$(cygpath -m "$WORK" 2>/dev/null || echo "$WORK")"
export MSYS_NO_PATHCONV=1

cleanup() {
  docker logs "$NAME" 2>&1 | tail -n 30 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker volume rm "$TMPVOL" >/dev/null 2>&1 || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "$WORK/uploads" "$WORK/data"
# mktemp -d is 0700 and owned by the runner user; the chown container below
# has only CAP_CHOWN (no DAC_READ_SEARCH), so it must be able to traverse it.
chmod 0755 "$WORK"
# The container user is uid/gid 10001; the bind mounts must be writable by it.
# chown from a throwaway root container so no sudo is needed (runner or laptop).
docker run --rm --user 0:0 --cap-drop ALL --cap-add CHOWN --entrypoint chown -v "$MOUNT:/w" "$IMAGE" -R 10001:10001 /w/uploads /w/data

docker run -d --name "$NAME" \
  --read-only --init -v "$TMPVOL:/tmp" \
  --memory 512m --memory-swap 512m --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -p "127.0.0.1:${PORT}:54000" \
  -v "$MOUNT/uploads:/app/uploads" -v "$MOUNT/data:/app/data" \
  -e RATE_LIMIT_SECONDS=0 -e GEO_IP_ENABLED=false \
  -e PUBLIC_BASE_URL="http://127.0.0.1:${PORT}" \
  "$IMAGE" >/dev/null

echo "== waiting for healthy"
status=starting
for _ in $(seq 1 40); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$NAME")"
  [ "$status" = healthy ] && break
  sleep 2
done
echo "health status: $status"
[ "$status" = healthy ] || { echo "::error::container did not become healthy"; exit 1; }

echo "== identity / filesystem"
user="$(docker exec "$NAME" id -u):$(docker exec "$NAME" id -g)"
echo "uid:gid = $user"
[ "$user" = "10001:10001" ] || { echo "::error::not running as 10001:10001"; exit 1; }
if docker exec "$NAME" sh -c 'touch /rootfs-write-test' 2>/dev/null; then
  echo "::error::root filesystem is writable"
  exit 1
fi
echo "root fs is read-only"

echo "== upload / download round trip"
head -c 65536 /dev/urandom > "$WORK/payload.bin"
resp="$(curl --connect-timeout 5 --max-time 180 -fsS -F "file=@$MOUNT/payload.bin;filename=payload.bin" "http://127.0.0.1:${PORT}/upload")"
url="$(printf '%s\n' "$resp" | head -n1)"
case "$url" in
  "http://127.0.0.1:${PORT}/download/"*) ;;
  *) echo "::error::unexpected download URL"; exit 1 ;;
esac
curl --globoff --proto '=http' --connect-timeout 5 --max-time 180 -fsS -o "$MOUNT/downloaded.bin" "$url"
cmp "$WORK/payload.bin" "$WORK/downloaded.bin"
echo "download matches upload: OK"

# Same /tmp (named volume) and memory limit as docker-compose.yaml: the app
# buffers uploads in memory and spools to /tmp, so a large file must still work.
echo "== 100 MB upload / download round trip"
head -c 104857600 /dev/urandom > "$WORK/big.bin"
resp="$(curl --connect-timeout 5 --max-time 180 -fsS -F "file=@$MOUNT/big.bin;filename=big.bin" "http://127.0.0.1:${PORT}/upload")"
url="$(printf '%s\n' "$resp" | head -n1)"
case "$url" in
  "http://127.0.0.1:${PORT}/download/"*) ;;
  *) echo "::error::unexpected download URL"; exit 1 ;;
esac
curl --globoff --proto '=http' --connect-timeout 5 --max-time 180 -fsS -o "$MOUNT/big-downloaded.bin" "$url"
cmp "$WORK/big.bin" "$WORK/big-downloaded.bin"
echo "100 MB download matches upload: OK"
