# Migration: container now runs as non-root (uid/gid 10001)

From this release the image runs as `10001:10001` (user `app`) instead of root,
with `/app` read-only for that user. Only `/app/uploads` and `/app/data` are
writable. Existing deployments must adapt **before** rolling the new image,
otherwise the app cannot write uploads or its `files_db.json`.

Fresh installs (empty directories or new volumes) need no action.

## Docker Compose host (bind mounts under /opt/temp-file-share)

1. Fix ownership of the existing data:

   ```sh
   sudo chown -R 10001:10001 /opt/temp-file-share/uploads /opt/temp-file-share/data
   ```

   If you changed `UPLOADS_HOST_DIR` or `DATA_HOST_DIR` in `.env`, chown those
   directories instead.

2. Pull and restart:

   ```sh
   docker compose pull && docker compose up -d
   ```

The compose file also sets `read_only: true` (with a named `tmp` volume on
`/tmp`), `cap_drop: ALL` and `no-new-privileges`.

## `docker run` with named volumes

Run this once, **before** starting the new image. Replace `uploads` and `data`
with your volume names if they differ (the README uses `uploads` and `data`):

```sh
docker run --rm --user 0 --entrypoint chown \
  -v uploads:/u -v data:/d \
  ghcr.io/nooblk-98/temp-file-share:<new> -R 10001:10001 /u /d
```

Then stop the old container and start the new one with the same `-v` flags.

## Rollback

Set `TAG` to the previous image tag (in `.env` or the shell) and run
`docker compose up -d`. For `docker run`, start the previous tag with the same
volumes. Files written by uid 10001 stay owned by it after rolling back, which
is harmless for the old root-run image.
