# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: builder -- assemble the app payload and a trimmed CPython runtime.
#
# The app is pure stdlib, so there is nothing to install; the whole size win
# comes from (a) alpine instead of debian-slim and (b) dropping the parts of
# CPython this service never imports.
#
# Pinned to 3.12: app.py imports `cgi` for multipart uploads, and `cgi` was
# removed in Python 3.13.
#
# Both stages use the SAME Alpine minor (3.23) so the builder's musl/libssl ABI
# matches the runtime. Bump the two FROM lines together; Dependabot will
# propose digest updates.
# ---------------------------------------------------------------------------
# python:3.12-alpine3.23
FROM python:3.12-alpine3.23@sha256:1fd55c2f838c4f76262f9eeed899ff9168ea96ac383c61667d6f204325e1f169 AS builder

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY backend.py app.py config.py _types.py filestore.py georesolver.py ratelimiter.py config.json ./
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

# Byte-compile ahead of time so the runtime (read-only, non-writable /app) never
# pays the compile cost or tries to write __pycache__ at import time.
RUN python -m compileall -q .

# Trim CPython: developer tooling, the test suite, and stdlib packages this
# service does not import. Their matching lib-dynload .so files go too, which
# is what lets the runtime stage skip sqlite/ncurses/readline/bz2/xz/gdbm.
#
# NOTE: after this trim, `import sqlite3|curses|readline|dbm|bz2|lzma|tkinter`
# will fail. Add the package back here (and its apk lib below) if code needs it.
WORKDIR /usr/local/lib/python3.12
RUN rm -rf test idlelib tkinter lib2to3 turtledemo pydoc_data ensurepip \
           sqlite3 dbm curses config-3.12-* \
           site-packages/pip site-packages/setuptools site-packages/pkg_resources \
           site-packages/pip-*.dist-info site-packages/setuptools-*.dist-info \
 && rm -f  lib-dynload/_sqlite3*.so lib-dynload/_curses*.so lib-dynload/readline*.so \
           lib-dynload/_dbm*.so lib-dynload/_gdbm*.so lib-dynload/_bz2*.so \
           lib-dynload/_lzma*.so lib-dynload/_tkinter*.so \
 && find . -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && find . -name '*.exe' -delete

WORKDIR /app

# ---------------------------------------------------------------------------
# Stage 2: runtime -- bare alpine plus only the shared libs the trimmed
# interpreter actually links against.
# ---------------------------------------------------------------------------
# alpine:3.23
FROM alpine:3.23@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0

LABEL org.opencontainers.image.title="temp-file-share" \
      org.opencontainers.image.description="Self-hosted temporary file sharing (pure-stdlib Python)" \
      org.opencontainers.image.source="https://github.com/nooblk-98/temp-file-share" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

# libssl3/libcrypto3 -> ssl+hashlib, libffi -> ctypes, libuuid -> uuid,
# zlib -> zipimport/gzip, ca-certificates -> outbound TLS from georesolver,
# tzdata -> makes the TZ env var take effect. `apk upgrade` pulls security
# fixes published since the pinned base; apk-tools is removed afterwards so the
# runtime image cannot install packages.
# Versions rotate with the digest-pinned Alpine base, so apk pins would rot.
# hadolint ignore=DL3018
RUN apk upgrade --no-cache \
 && apk add --no-cache libssl3 libcrypto3 libffi libuuid zlib ca-certificates tzdata \
 && apk del --no-cache apk-tools \
 && rm -rf /var/cache/apk/*

COPY --from=builder /usr/local/bin/python3.12 /usr/local/bin/python3.12
COPY --from=builder /usr/local/lib/libpython3.12.so.1.0 /usr/local/lib/
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
RUN ln -s /usr/local/bin/python3.12 /usr/local/bin/python3 \
 && ln -s /usr/local/bin/python3.12 /usr/local/bin/python

# Fixed non-root identity (uid/gid 10001). /app stays root-owned, so it is
# read-only for the app user; only uploads/ and data/ are writable by it.
RUN addgroup -g 10001 -S app \
 && adduser -u 10001 -S -G app -H -h /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /app /app
RUN mkdir -p /app/uploads /app/data \
 && chown 10001:10001 /app/uploads /app/data \
 && chmod 0750 /app/uploads /app/data \
 && chmod 0644 /app/config.json

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER 10001:10001

EXPOSE 54000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python3", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:54000/robots.txt', timeout=4).status == 200 else 1)"]

CMD ["python3", "backend.py"]
