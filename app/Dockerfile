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
# ---------------------------------------------------------------------------
FROM python:3.12-alpine AS builder

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
RUN cd /usr/local/lib/python3.12 \
 && rm -rf test idlelib tkinter lib2to3 turtledemo pydoc_data ensurepip \
           sqlite3 dbm curses config-3.12-* \
           site-packages/pip site-packages/setuptools site-packages/pkg_resources \
 && rm -f  lib-dynload/_sqlite3*.so lib-dynload/_curses*.so lib-dynload/readline*.so \
           lib-dynload/_dbm*.so lib-dynload/_gdbm*.so lib-dynload/_bz2*.so \
           lib-dynload/_lzma*.so lib-dynload/_tkinter*.so \
 && find . -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && find . -name '*.exe' -delete

# ---------------------------------------------------------------------------
# Stage 2: runtime -- bare alpine plus only the shared libs the trimmed
# interpreter actually links against.
# ---------------------------------------------------------------------------
FROM alpine:3.21

# libssl3/libcrypto3 -> ssl+hashlib, libffi -> ctypes, libuuid -> uuid,
# zlib -> zipimport/gzip, ca-certificates -> outbound TLS from georesolver.
RUN apk add --no-cache libssl3 libcrypto3 libffi libuuid zlib ca-certificates \
 && rm -rf /var/cache/apk/*

COPY --from=builder /usr/local/bin/python3.12 /usr/local/bin/python3.12
COPY --from=builder /usr/local/lib/libpython3.12.so.1.0 /usr/local/lib/
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
RUN ln -s /usr/local/bin/python3.12 /usr/local/bin/python3 \
 && ln -s /usr/local/bin/python3.12 /usr/local/bin/python

WORKDIR /app
COPY --from=builder /app /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 54000

CMD ["python3", "backend.py"]
