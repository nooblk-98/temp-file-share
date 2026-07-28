# temp-file-share Domain Context

## Domain Vocabulary

- **Upload** — a file or tarball sent by a client via POST /upload, stored on disk with a UUID-prefixed filename, and made available for download.
- **Download** — retrieving a stored file by its UUID-prefixed filename via GET /download/<filename>.
- **IP Quota** — storage limit enforced per client IP address. Configurable via `IP_LIMIT_GB`.
- **Expiry** — automatic deletion of uploads older than `MAX_AGE_HOURS`, enforced by a background cleanup thread.
- **File Metadata** — the record of an upload: filename, size in bytes, upload timestamp. Persisted as JSON.
- **Cleanup** — the background process that walks metadata, identifies expired entries, deletes the corresponding files, and persists the updated metadata.

## Architecture

- **Monolithic backend** — all server logic in `app/app.py` (~388 lines), supported by extracted modules.
- **Zero external dependencies** — Python stdlib only.
- **Client upload script** — `upload.sh` (bash), uses `curl` and `tar`.

## Modules (post-refactor)

| Module | Responsibility | Interface |
|--------|---------------|-----------|
| `app.py` | HTTP handler, routing, template rendering, entry point | `run(config_path?)` |
| `_types.py` | Domain types shared across modules | `Config`, `FileEntry`, `IPAddress` |
| `config.py` | Load and validate configuration from JSON | `load_config(base_dir) -> Config` |
| `filestore.py` | File + metadata persistence | `FileStore` protocol — `DiskFileStore`, `InMemoryFileStore` |
| `georesolver.py` | IP-to-country-code resolution | `GeoResolver` protocol — `HttpGeoResolver`, `NullGeoResolver` |
| `ratelimiter.py` | Per-IP rate limiting | `RateLimiter.allow(ip) -> bool` |
| `backend.py` | Entry-point shim | `from app import run; run()` |
| `upload.sh` | Client-side CLI (single copy in `app/scripts/`) | CLI for `curl` + `tar` uploads |
