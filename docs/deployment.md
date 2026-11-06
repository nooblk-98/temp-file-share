# Deployment options

All three Compose files use the same hardened runtime and application configuration. Choose one explicitly; do not combine the files as overrides.

| Stack | Compose file | Image/build | Default port | Default persistent directories |
| --- | --- | --- | --- | --- |
| Stable | `docker-compose.yaml` | GHCR `live` release image | 34100 | `/opt/temp-file-share/{uploads,data}` |
| Development | `docker-compose.dev.yaml` | GHCR `development` image | 34101 | `/opt/temp-file-share-dev/{uploads,data}` |
| Source | `docker-compose.source.yaml` | Local `temp-file-share:source` build | 34102 | `/opt/temp-file-share-source/{uploads,data}` |

Project names, container names, temporary volumes, storage, and default ports are distinct, so the stacks can coexist on a fresh host. Preserve your existing `.env`/Portainer environment overrides during upgrades. All stacks bind loopback by default; a remote/tunnel proxy needs an explicitly reachable private binding and exact proxy trust.

## Stable: published release image

The [main README](../README.md#deploy-the-stable-image) contains the fresh-install command. For a configured stack:

```bash
docker compose up -d --pull always
```

Stable tags at `ghcr.io/nooblk-98/temp-file-share`:

- `live` and `latest`: latest successfully published stable release, never a branch push.
- `2.2.0` and `v2.2.0`: a specific release's image.
- `@sha256:…`: a content-addressed manifest pin for exact reproduction.

For version pinning, set `IMAGE_TAG=2.2.0` in `.env`. For a digest pin, use a small local override:

```yaml
# compose.pin.yaml
services:
  backend:
    image: ghcr.io/nooblk-98/temp-file-share@sha256:REPLACE_WITH_VERIFIED_DIGEST
```

```bash
docker compose -f docker-compose.yaml -f compose.pin.yaml up -d --pull always
```

For rollback, restore the previous version/digest and re-run the same command. Back up uploads and metadata together while stopped before changing versions; do not roll back storage blindly across incompatible formats.

## Development: latest tested branch image

Use a separate checkout/configuration and a separate Portainer stack if needed:

```bash
cp .env.dev.example .env.dev
sudo install -d -o 10001 -g 10001 /opt/temp-file-share-dev/uploads /opt/temp-file-share-dev/data
docker compose --env-file .env.dev -f docker-compose.dev.yaml up -d --pull always
```

Open `http://localhost:34101`. `development` moves to the latest tested branch head; `development-sha-<full commit SHA>` identifies an individual successful commit build. Set `DEV_IMAGE_TAG` to pin one of those builds. Older builds may publish their SHA tag but cannot move the channel over a newer head.

The default port, binding, URL, storage, and proxy trust use `DEV_HOST_PORT`, `DEV_HOST_BIND`, `DEV_PUBLIC_BASE_URL`, `DEV_UPLOADS_HOST_DIR`, `DEV_DATA_HOST_DIR`, and `DEV_TRUSTED_PROXIES`. A production `.env` cannot silently redirect these to production storage. See [development deployment automation](development-deployment.md) before enabling its webhook.

## Build and run from source

Clone a release/tag or the branch you intend to test. The source stack builds the same `app/Dockerfile` as CI and tags it locally; it does not download the application image from GHCR or require registry credentials.

```bash
git clone --branch v2.2.0 https://github.com/nooblk-98/temp-file-share.git
cd temp-file-share
sudo install -d -o 10001 -g 10001 /opt/temp-file-share-source/uploads /opt/temp-file-share-source/data
docker compose -f docker-compose.source.yaml up -d --build
```

Open `http://localhost:34102`. Use `SOURCE_HOST_PORT`, `SOURCE_HOST_BIND`, `SOURCE_PUBLIC_BASE_URL`, `SOURCE_UPLOADS_HOST_DIR`, `SOURCE_DATA_HOST_DIR`, and `SOURCE_TRUSTED_PROXIES` for source-stack overrides. `SOURCE_IMAGE` changes the local image name (default `temp-file-share:source`).

To build just the image without starting a stack:

```bash
docker build -t temp-file-share:source app
```

To run Python directly instead, use Python 3.11+:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/requirements.txt
PUBLIC_BASE_URL=http://localhost:54000 python app/backend.py
```

## Verify an image and running service

```bash
docker buildx imagetools inspect ghcr.io/nooblk-98/temp-file-share:live
docker compose ps
curl -fsS http://localhost:34100/robots.txt
```

The multi-platform index contains linux/amd64 and linux/arm64 plus build attestations. The package is public, so pulls do not need credentials. Inspect the version/digest in the [package page](https://github.com/nooblk-98/temp-file-share/pkgs/container/temp-file-share) or image-publishing workflow before pinning it.

A healthy local container is not proof of a working public proxy route. Verify the public hostname from the requesting client too. Keep host bindings/proxy peer values in private stack settings, not the public repository.
