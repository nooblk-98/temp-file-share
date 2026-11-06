# Release notes

## v2.2.0 — GHCR image channels and deployment organization

### Container publishing

- Publish a commit-specific GHCR image for every successful push to `development`; promote the tested current branch head to the `development` channel.
- Publish stable version tags only from a published stable GitHub release whose commit belongs to `main`. Promote the latest stable release to `live` and `latest` after image smoke tests.
- Build linux/amd64 and linux/arm64 images with provenance and SBOM metadata, using the same Dockerfile for both channels and source builds.
- Authenticate with the repository-scoped `GITHUB_TOKEN`; no Docker Hub credentials or long-lived package token is required.
- Trigger stable Portainer redeployment only after the live image is available. Separate development-stack deployment is opt-in to avoid redeploying production with a development webhook.

### Deployment and documentation

- Make `docker-compose.yaml` pull the stable `live` image instead of building on the server.
- Add `docker-compose.dev.yaml` for the development image and `docker-compose.source.yaml` for local source builds, with independent default ports, storage, project names, and container names.
- Add a stable-image one-command deployment to the main README and document pinning, rollback, image automation, and source builds separately.
- Add `CONTRIBUTING.md` and a Contributions welcome section.
- Pin Actions to full commit SHAs, refresh the official build Actions, and use Ubuntu 24.04 for reproducible browser dependencies.

### Upgrade from v2.1.0

- The stable stack retains `/opt/temp-file-share/uploads`, `/opt/temp-file-share/data`, port 34100, uid/gid 10001, and all resource/security controls. Keep your existing `.env` and Portainer stack environment settings, especially the proxy-reachable `HOST_BIND` and exact `TRUSTED_PROXIES`.
- Replace `docker compose up -d --build` with `docker compose up -d --pull always` for the stable image. The source-build command is now `docker compose -f docker-compose.source.yaml up -d --build`.
- The alternative stacks use their own storage by default; they do not silently reuse or move production uploads. Review their documented environment variables before deployment.
- For a Portainer Git stack, select the matching Compose filename and re-pull its image when redeploying. Use a separate stack/webhook for development; do not reuse the live stack webhook.
- Earlier source-only releases remain available by tag; no existing Git tags are moved.

## v2.1.0 — 2026-11-06

Security, reliability, and documentation refresh.

This release includes the security fixes, documentation refresh, hardened source-build deployment, and development automation delivered since v2.0.3.

### Security

- Confine downloads to the uploads directory; reject path traversal, absolute paths, NULs, symlinks, unregistered files, and expired records.
- Sanitize upload filenames and provide safe ASCII/UTF-8 attachment headers.
- Ignore forwarded client-IP and protocol headers unless the socket peer is explicitly listed in `TRUSTED_PROXIES`. Walk forwarded chains from the nearest proxy.
- Scope `/uploads` to the visitor's current IP. Remove public uploader-IP/country columns and external IP-geolocation requests. Add no-store/no-referrer/nosniff response headers.
- Reject cross-site browser clear requests. This remains an IP-scoped service, not an authenticated user store; people sharing an IP can manage the same files.
- Bind Compose to loopback by default. Main deployment configuration is preserved.

### Transfers and storage

- Replace `cgi` with pinned `python-multipart` streaming parsing; raise the supported source minimum to Python 3.11. Rename `_types.py` to avoid a Python 3.14 standard-library module-name collision.
- Stream uploads and downloads in 64 KiB chunks. Enforce `MAX_UPLOAD_MB`, validate request framing, reserve quota before reading bodies, and discard incomplete temporary uploads.
- Use bounded threaded handlers with inactivity timeouts; slow transfers no longer serialize all requests. Limit concurrent handlers with `MAX_CONNECTIONS`.
- Serialize metadata operations and cleanup with a reentrant lock; write JSON to a temporary file, fsync, and atomically replace it. Fail closed on corrupt JSON instead of forgetting file ownership. Prune records for missing files; retry scheduled cleanup after errors.
- Check expiry on each download even between cleanup passes.

### Browser and CLI

- Return `Retry-After` on HTTP 429; the browser waits and retries cooldown responses, up to three times. Failed queues no longer claim success.
- Show maximum file size, reject oversized selections, handle upload timeout/abort, and disable file selection while a queue runs.
- Update the uploads list after clearing; add live status announcements, visible keyboard focus, theme-aware errors, safe long-filename wrapping, and contained table scrolling on mobile.
- Point the client to `fs.app.itsnooblk.com`; serve it with the instance's configured origin. Propagate curl/tar failures, use unique temporary archives with cleanup, and use GNU/BSD-compatible tar options.

### Documentation and automation

- Recreate the README with a native SVG banner, real light/dark/mobile screenshots, setup/configuration/API guidance, and an explicit privacy/operating model.
- Remove stale claims about missing CI/release/image-signing workflows and published-image-based Compose deployment.
- Add Python 3.11–3.14 regression CI, Docker smoke verification, and browser workflow/responsive tests.
- Add a development-only Portainer deployment action gated by reusable CI. Keep the webhook in `PORTAINER_DEVELOPMENT_WEBHOOK_URL`, not source control. Keep the existing main workflow/secret unchanged.

### Upgrade notes

1. **Back up uploads and metadata together while the server is stopped.** The JSON schema is unchanged; existing records remain readable. Run only one process/replica against a storage directory.
2. **Source installs:** use Python 3.11+ and install `app/requirements.txt`. The zero-external-dependencies claim no longer applies. Docker installs the parser during its build.
3. **Set proxy trust deliberately:** empty `TRUSTED_PROXIES` ignores forwarding headers. Until the exact proxy peer is configured, proxied users share the proxy's IP quota/list. Do not trust arbitrary networks; ensure the proxy overwrites incoming headers and blocks direct backend access.
4. **Check networking:** Compose now binds `127.0.0.1:34100` by default. A proxy running in another container needs a private shared network or a deliberately configured bind. Do not change the internal port from 54000 with the supplied healthcheck/mapping.
5. **Review limits:** the default maximum file size is 1024 MiB, with up to 64 KiB multipart overhead. Socket inactivity timeout defaults to 30 seconds, concurrent handlers to 16. Streaming removes the prior whole-file RAM requirement; disk capacity still matters.
6. **Review visibility:** `/uploads` is now IP-scoped, has no public IP/country columns, and does not perform IP geolocation. `GEO_IP_ENABLED` is retired. Shared-IP users still share management access.
7. **Configure Portainer:** select `refs/heads/development` in the development Git stack, enable rebuilding from the repository's Compose source, and set the repository secret. The action does not reconfigure the Portainer stack or deploy feature branches.
8. **Rebuild:** `docker compose up -d --build`. Verify health, upload/download, your uploads, and clear using disposable files. Rollback requires the previous source/image and matching Python requirements; retain your backup.

See [UI review](docs/ui-review/README.md) for screenshot provenance and verification details.
