# temp-file-share domain context

A single-process, bounded-threaded HTTP service for temporary browser/CLI file sharing. Python 3.11+; one runtime dependency (`python-multipart`). No separate database service or frontend build.

| Module | Responsibility |
| --- | --- |
| `app/app.py` | Routes, trusted-proxy identity, safe filenames, HTML, streamed downloads, bounded HTTP server |
| `app/models.py` | Immutable configuration and file metadata types |
| `app/config.py` | JSON/environment configuration and validation |
| `app/filestore.py` | Confined storage, quota reservations, metadata lock/atomic replacement, expiry |
| `app/uploads.py` | Bounded raw and multipart body ingestion |
| `app/ratelimiter.py` | Thread-safe per-IP cooldown with expiring entries |
| `app/backend.py` | Entry-point shim |
| `app/scripts/upload.sh` | Bash/curl/tar client |
| `tests/` | Backend security/regression tests and browser workflows |

## Invariants

- Downloads must name a recorded, unexpired, non-symlink file directly inside uploads.
- Client IP comes from the socket unless that peer is an explicitly trusted proxy.
- Quota is reserved for the complete Content-Length before reading; transfers use bounded chunks.
- JSON read/modify/write and cleanup share one reentrant lock. Writes replace metadata atomically. One process per storage directory; no shared-volume replicas.
- Lists and clear operations are IP-scoped, not authenticated. NAT/VPN peers share access.
- Main deployment remains separate; development deployment runs only from development after reusable CI passes. Webhook credentials live only in GitHub Actions secrets.

See README.md for operational configuration and RELEASE_NOTES.md for migrations.
