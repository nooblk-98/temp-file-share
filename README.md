<div align="center">

<img src="images/banner.svg" alt="Temp File Share — Upload. Share. Let it expire." width="100%" />

# Temp File Share

**Self-hosted temporary file sharing, from your browser or terminal.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white)](app/pyproject.toml)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed?logo=docker&logoColor=white)](docker-compose.yaml)
[![CI](https://github.com/nooblk-98/temp-file-share/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/nooblk-98/temp-file-share/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-0f6b5e)](LICENSE)

[Live instance](https://fs.app.itsnooblk.com/) · [Quick start](#quick-start) · [Screenshots](#screenshots) · [Self-host](#self-host) · [Release notes](RELEASE_NOTES.md)

</div>

Upload a file, copy its download link, and let the server clean it up later. Use drag-and-drop in the web UI, or send files and folders with the Bash client. No accounts, database service, or frontend build step.

> **Upgrading to v2.1.0?** Read the [upgrade notes](RELEASE_NOTES.md#upgrade-notes) for Python requirements, trusted proxy configuration, and storage migration. Previously published container images may still run an older version.

## At a glance

| Share simply | Stay in control | Run it yourself |
| --- | --- | --- |
| Browser uploads with progress and copyable links | Configurable expiry, total storage, and per-IP quotas | Python 3.11+ with one streaming-parser dependency |
| Bash client archives folders and multiple paths | Per-request size limits and bounded concurrent transfers | Non-root, read-only Docker container |
| Light/dark themes and responsive layouts | Your uploads page shows only your current IP's files | Local JSON metadata; no external database |

## Screenshots

Actual locally rendered application pages, using synthetic files—not design mockups or production user data. Both themes retain the same layout and controls.

### Browser upload · light

![Browser upload in the light theme](docs/ui-review/after-home-light-rounded.svg)

<details>
<summary><strong>Dark theme, uploads page, and mobile</strong></summary>

### Browser upload · dark

![Browser upload in the dark theme](docs/ui-review/after-home-dark-rounded.svg)

### Your uploads

Only uploads associated with the visitor's current IP are shown. Filenames link to downloads; public IP/country columns have been removed.

![Your uploads page](docs/ui-review/after-uploads-light-rounded.svg)

### Mobile · 390 px

<img src="docs/ui-review/after-home-mobile-rounded.svg" width="390" alt="Mobile browser upload page" />

</details>

Screenshot provenance and before/after comparisons: [UI review](docs/ui-review/README.md).

## Quick start

### Browser

Open [fs.app.itsnooblk.com](https://fs.app.itsnooblk.com/), choose or drop your files, then select **Upload**. Each successful file gets its own download link. **Your uploads** lists files associated with your current IP.

### Terminal

Download the client, then run it:

```bash
curl -fsS https://fs.app.itsnooblk.com/upload.sh -o upload.sh
bash upload.sh document.pdf
```

```bash
# A folder or multiple paths become one .tar.gz archive
bash upload.sh photos/ notes.txt

# Another server
BACKEND_URL=https://files.example.com bash upload.sh document.pdf

# Delete uploads associated with your current IP
bash upload.sh --clear
```

The client requires Bash, curl, and tar (GNU/Linux or macOS). Upload failures exit nonzero; temporary archives use a unique directory and are cleaned up on exit.

## Self-host

### Docker Compose — build from source

Compose builds the checked-out source. It does **not** pull a GHCR image or use a `TAG` variable.

```bash
git clone --branch v2.1.0 https://github.com/nooblk-98/temp-file-share.git
cd temp-file-share
cp .env.example .env
sudo mkdir -p /opt/temp-file-share/uploads /opt/temp-file-share/data
sudo chown 10001:10001 /opt/temp-file-share/uploads /opt/temp-file-share/data
# Edit .env: set your public URL, quotas, and trusted proxy peers.
docker compose up -d --build
```

Default host binding: **127.0.0.1:34100**, mapped to container port **54000**. Put a TLS reverse proxy in front. For container-to-container proxying, use a private shared Docker network and configure only that proxy's peer address in `TRUSTED_PROXIES`.

The container uses uid/gid `10001:10001`, a read-only root filesystem, dropped capabilities, no-new-privileges, resource limits, and rotated logs. Uploads and metadata are persisted in the two bind mounts. Existing root-owned volumes need the [non-root migration](docs/MIGRATION-nonroot.md).

### Run from source

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
PUBLIC_BASE_URL=http://localhost:54000 python app/backend.py
```

Requires **Python 3.11+**. The Docker image uses Python 3.12. Multipart parsing uses the maintained [`python-multipart`](https://multipart.fastapiexpert.com/) library instead of the removed standard-library `cgi` module.

### Configuration

Environment variables override `app/config.json`. Compose forwards the variables in [.env.example](.env.example). Sizes use binary units: GB = GiB, MB = MiB.

| Setting | Shipped default | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | `https://fs.app.itsnooblk.com` | Public origin used for links and the served upload client; change for your host |
| `UPLOAD_DIR` | `uploads` | Stored files; relative to `app/` |
| `FILES_DB` | `data/files_db.json` | JSON metadata; relative to `app/` |
| `MAX_STORAGE_GB` | `50` | Total disk quota |
| `IP_LIMIT_GB` | `10` | Quota shared by one client IP |
| `MAX_UPLOAD_MB` | `1024` | Maximum file size per request |
| `MAX_AGE_HOURS` | `5` | Download lifetime |
| `RATE_LIMIT_SECONDS` | `2` | Upload-start cooldown per IP; `0` disables it |
| `CLEANUP_INTERVAL_SECONDS` | `300` | Background expiry cleanup interval |
| `TRUSTED_PROXIES` | empty | Comma-separated proxy peer IPs/CIDRs; empty ignores forwarded headers |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Socket inactivity timeout—not total transfer duration |
| `MAX_CONNECTIONS` | `16` | Concurrent handler limit; excess requests receive 503 |
| `PORT` | `54000` | Source server port; keep 54000 inside the provided container |

Compose-specific defaults: `HOST_BIND=127.0.0.1`, `HOST_PORT=34100`, `MEM_LIMIT=512m`, `CPU_LIMIT=1.0`, `PIDS_LIMIT=256`, and `TZ=Asia/Colombo`.

Transfers use 64 KiB chunks rather than buffering entire files in RAM. Temporary uploads live on the uploads filesystem and count against reserved quota before the request body is read. Multipart requests reserve their complete body size, so leave a little quota headroom for headers and boundaries (up to 64 KiB). Keep sufficient disk space and tune concurrency for your host.

### Reverse proxy example

For nginx running on the same host as Compose:

```nginx
location / {
    proxy_pass http://127.0.0.1:34100;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 1025m; # 1024 MiB file plus multipart overhead
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

Set `PUBLIC_BASE_URL` to your HTTPS origin. Set `TRUSTED_PROXIES` to the exact peer address the application sees for nginx—Docker may present a bridge gateway, not `127.0.0.1`. The proxy must **overwrite** incoming forwarding headers. Do not trust `0.0.0.0/0` or expose the backend directly when proxy trust is enabled.

### Development deployments with Portainer

[Deploy development to Portainer](.github/workflows/deploy-development.yml) runs on pushes to `development`, or manually when that branch is selected. It first calls the reusable [CI workflow](.github/workflows/ci.yml); only successful checks trigger the stack webhook. Feature-branch pushes and PRs do not deploy.

Configure the GitHub repository secret **`PORTAINER_DEVELOPMENT_WEBHOOK_URL`** with the development stack's webhook. Configure that Portainer Git stack to track **`refs/heads/development`**, use `docker-compose.yaml`, and rebuild the source when redeploying. The webhook requests a redeploy; it does not change the stack's Git ref or configuration. The existing `main` deployment workflow and its `DEPLOY_WEBHOOK_URL` secret are separate and unchanged.

No webhook URL is committed or printed. A successful webhook request means Portainer accepted it; confirm container health in Portainer after deployment.

## API

| Method | Route | Result |
| --- | --- | --- |
| `POST` | `/upload` | One multipart `file` or raw body; plain-text response, first line is the download URL |
| `GET` | `/download/<stored-name>` | Attachment download while the recorded file is unexpired |
| `GET` | `/uploads` | HTML listing scoped to the visitor's current IP |
| `POST` | `/clear` | Deletes uploads associated with the visitor's current IP |
| `GET` | `/upload.sh` | Client script configured for this server |
| `GET` | `/robots.txt` | Lightweight container healthcheck target |

```bash
# Multipart upload, preserving the original filename
curl -fsS -F 'file=@photo.jpg' https://files.example.com/upload

# Raw upload, stored with a generated .bin filename
curl -fsS -H 'Content-Type: application/octet-stream' \
  --data-binary @photo.jpg https://files.example.com/upload
```

Uploads require `Content-Length`; chunked request bodies are not supported. Common responses: **400** malformed upload, **411** missing length, **413** size/quota exceeded, **429** cooldown (`Retry-After` supplied), and **503** all connection slots busy. The browser retries cooldown responses up to three times and keeps failed uploads visibly marked.

## Privacy and operating model

- **No accounts or passwords:** links are bearer links. Anyone given a link can download its file until expiry; files are not end-to-end encrypted.
- **IP-scoped, not user-authenticated:** people sharing a NAT/VPN/public IP share the uploads list, quota, and clear operation. Changing IP changes the visible list. Use a private deployment when that model is unsuitable.
- **No public upload directory:** paths must remain inside storage and refer to a recorded, unexpired file. The uploads UI no longer publishes IP addresses or performs external IP geolocation.
- **Expiry:** downloads stop at expiry; physical deletion happens on the next cleanup pass. Maintain backups according to your retention needs.
- **One server process per storage directory:** a process-local lock and atomic JSON replacement protect concurrent requests and cleanup. Do not point multiple replicas at the same JSON database. Stop the server before backing up or restoring both persistent directories together. Corrupt metadata fails closed; restore a known-good copy rather than resetting it.
- HTTP access logs and the metadata file still contain IPs for operations/quota ownership. The UI loads Google Fonts; self-host fonts if your deployment must avoid that external request.

## Development and checks

```bash
python -m pip install -r app/requirements.txt ruff==0.17.4
ruff check app tests
python -m unittest discover -s tests -v

cd tests/browser
npm ci
npx playwright install chromium
PYTHON=python npm test
```

CI runs regression tests on Python **3.11–3.14**, a hardened Docker upload/download smoke test, and Chromium workflow/responsive checks at **320, 390, 768, 1024, and 1440 px**, in light and dark themes. There is currently **no image-publish, signing, SBOM, or release-creation workflow**; this README does not imply those exist.

```text
app/                   HTTP service, storage, streaming parser, UI, Bash client
tests/                 Backend regression tests and Playwright browser checks
docs/ui-review/        Real screenshots, provenance, before/after evidence
.github/workflows/     CI, existing main deployment, development deployment
docker-compose.yaml    Hardened source-build deployment
RELEASE_NOTES.md        Release changes and migration guidance
```

## License

[GNU Affero General Public License v3.0](LICENSE).
