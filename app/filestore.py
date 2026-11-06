from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import BinaryIO, Iterator

from models import FileEntry, IPAddress

logger = logging.getLogger("temp-file-share")


class QuotaExceeded(ValueError):
    pass


class DiskFileStore:
    """Single-process store. One lock covers every metadata read/modify/write."""

    def __init__(self, upload_dir: str, files_db: str) -> None:
        self._upload_dir = Path(upload_dir).resolve()
        self._files_db = Path(files_db)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._files_db.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._reservations: dict[str, int] = {}
        # Fail closed on corruption: do not silently forget ownership/expiry.
        with self._lock:
            self._load_db()
        # Only one server process may own this store. Remove interrupted uploads.
        for path in self._upload_dir.glob(".incoming-*"):
            path.unlink()

    def _load_db(self) -> dict[IPAddress, list[FileEntry]]:
        if not self._files_db.exists():
            return {}
        with self._files_db.open(encoding="utf-8") as stream:
            raw = json.load(stream)
        return {
            IPAddress(ip): [
                FileEntry(str(e["filename"]), int(e["size"]), float(e["time"])) for e in entries
            ]
            for ip, entries in raw.items()
        }

    def _save_db(self, db: dict[IPAddress, list[FileEntry]]) -> None:
        raw = {ip: [vars(entry) for entry in entries] for ip, entries in db.items()}
        fd, name = tempfile.mkstemp(prefix=".metadata-", dir=self._files_db.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(raw, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._files_db)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _safe_path(self, name: str) -> Path | None:
        if not name or name in (".", "..") or any(c in name for c in ("/", "\\", "\x00")):
            return None
        path = self._upload_dir / name
        if path.is_symlink() or path.resolve().parent != self._upload_dir:
            return None
        return path

    @contextlib.contextmanager
    def reserve(self, ip: str, size: int, total_limit: int, ip_limit: int) -> Iterator[None]:
        """Reserve the request length before reading; includes multipart overhead."""
        with self._lock:
            if self.used_bytes() + sum(self._reservations.values()) + size > total_limit:
                raise QuotaExceeded("Not enough allocated space")
            if self.used_bytes_by_ip(ip) + self._reservations.get(ip, 0) + size > ip_limit:
                raise QuotaExceeded("IP limit exceeded. Clear your uploads and retry.")
            self._reservations[ip] = self._reservations.get(ip, 0) + size
        try:
            yield
        finally:
            with self._lock:
                self._reservations[ip] -= size
                if not self._reservations[ip]:
                    del self._reservations[ip]

    def commit(self, ip: str, filename: str, temporary: str) -> FileEntry:
        with self._lock:
            path = self._safe_path(filename)
            if path is None or path.exists():
                raise ValueError("Invalid or existing filename")
            db = self._load_db()
            entry = FileEntry(filename, os.path.getsize(temporary), time.time())
            os.replace(temporary, path)
            db.setdefault(IPAddress(ip), []).append(entry)
            try:
                self._save_db(db)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return entry

    def store(self, ip: str, filename: str, data: bytes) -> FileEntry:
        """Fixture/convenience API; HTTP uploads use a streamed temporary file."""
        fd, name = tempfile.mkstemp(prefix=".incoming-", dir=self._upload_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            return self.commit(ip, filename, name)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def open_download(self, filename: str, max_age_seconds: float) -> BinaryIO | None:
        with self._lock:
            path = self._safe_path(filename)
            if path is None:
                return None
            entries = (e for files in self._load_db().values() for e in files)
            if not any(
                e.filename == filename and time.time() - e.time <= max_age_seconds for e in entries
            ):
                return None
            try:
                return path.open("rb")
            except (FileNotFoundError, IsADirectoryError):
                return None

    def delete_by_ip(self, ip: str) -> int:
        with self._lock:
            db = self._load_db()
            entries = db.pop(IPAddress(ip), [])
            for entry in entries:
                path = self._safe_path(entry.filename)
                if path is not None:
                    path.unlink(missing_ok=True)
            if entries:
                self._save_db(db)
            return len(entries)

    def delete_expired(self, max_age_seconds: float) -> int:
        with self._lock:
            db = self._load_db()
            now = time.time()
            removed = 0
            for ip, files in list(db.items()):
                kept = []
                for entry in files:
                    path = self._safe_path(entry.filename)
                    if path is None or not path.is_file() or now - entry.time > max_age_seconds:
                        if path is not None:
                            path.unlink(missing_ok=True)
                        removed += 1
                    else:
                        kept.append(entry)
                if kept:
                    db[ip] = kept
                else:
                    del db[ip]
            if removed:
                self._save_db(db)
            return removed

    def list_by_ip(self, ip: str) -> list[FileEntry]:
        with self._lock:
            return list(self._load_db().get(IPAddress(ip), []))

    def used_bytes(self) -> int:
        with self._lock:
            return sum(
                p.stat().st_size
                for p in self._upload_dir.iterdir()
                if p.is_file() and not p.name.startswith(".incoming-")
            )

    def used_bytes_by_ip(self, ip: str) -> int:
        with self._lock:
            return sum(e.size for e in self.list_by_ip(ip))

    def entries(self) -> dict[IPAddress, list[FileEntry]]:
        with self._lock:
            return self._load_db()
