from __future__ import annotations

import json
import logging
import os
import time
from typing import Protocol

from _types import IPAddress, FileEntry

logger = logging.getLogger("temp-file-share")


class FileStore(Protocol):
    def store(self, ip: str, filename: str, data: bytes) -> FileEntry: ...

    def retrieve(self, uuid_name: str) -> bytes | None: ...

    def delete_by_ip(self, ip: str) -> int: ...

    def delete_expired(self, max_age_seconds: float) -> int: ...

    def list_by_ip(self, ip: str) -> list[FileEntry]: ...

    def used_bytes(self) -> int: ...

    def used_bytes_by_ip(self, ip: str) -> int: ...

    def entries(self) -> dict[IPAddress, list[FileEntry]]: ...


class DiskFileStore:
    def __init__(self, upload_dir: str, files_db: str) -> None:
        self._upload_dir = upload_dir
        self._files_db = files_db
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(os.path.dirname(files_db), exist_ok=True)

    def _load_db(self) -> dict[IPAddress, list[FileEntry]]:
        if not os.path.exists(self._files_db):
            return {}
        try:
            with open(self._files_db) as f:
                raw: dict[str, list[dict[str, object]]] = json.load(f)
        except json.JSONDecodeError:
            logger.warning("corrupt db, resetting")
            return {}
        result: dict[IPAddress, list[FileEntry]] = {}
        for ip, entries in raw.items():
            result[IPAddress(ip)] = [
                FileEntry(
                    filename=str(e.get("filename", "")),
                    size=int(e.get("size", 0)),
                    time=float(e.get("time", 0.0)),
                )
                for e in entries
            ]
        return result

    def _save_db(self, db: dict[IPAddress, list[FileEntry]]) -> None:
        raw: dict[str, list[dict[str, object]]] = {
            ip: [
                {"filename": e.filename, "size": e.size, "time": e.time}
                for e in entries
            ]
            for ip, entries in db.items()
        }
        with open(self._files_db, "w") as f:
            json.dump(raw, f)

    def store(self, ip: str, filename: str, data: bytes) -> FileEntry:
        db = self._load_db()
        filepath = os.path.join(self._upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        entry = FileEntry(filename=filename, size=len(data), time=time.time())
        ip_files = db.get(IPAddress(ip), [])
        ip_files.append(entry)
        db[IPAddress(ip)] = ip_files
        self._save_db(db)
        return entry

    def retrieve(self, uuid_name: str) -> bytes | None:
        filepath = os.path.join(self._upload_dir, uuid_name)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "rb") as f:
            return f.read()

    def delete_by_ip(self, ip: str) -> int:
        db = self._load_db()
        ip_files = db.pop(IPAddress(ip), [])
        count = 0
        for entry in ip_files:
            filepath = os.path.join(self._upload_dir, entry.filename)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    count += 1
                except OSError:
                    pass
        self._save_db(db)
        return count

    def delete_expired(self, max_age_seconds: float) -> int:
        db = self._load_db()
        now = time.time()
        removed = 0
        for ip, files in list(db.items()):
            kept: list[FileEntry] = []
            for entry in files:
                filepath = os.path.join(self._upload_dir, entry.filename)
                if os.path.exists(filepath) and now - entry.time > max_age_seconds:
                    os.remove(filepath)
                    removed += 1
                else:
                    kept.append(entry)
            if kept:
                db[ip] = kept
            else:
                del db[ip]
        self._save_db(db)
        return removed

    def list_by_ip(self, ip: str) -> list[FileEntry]:
        return list(self._load_db().get(IPAddress(ip), []))

    def used_bytes(self) -> int:
        total = 0
        for fname in os.listdir(self._upload_dir):
            fpath = os.path.join(self._upload_dir, fname)
            if os.path.isfile(fpath):
                total += os.path.getsize(fpath)
        return total

    def used_bytes_by_ip(self, ip: str) -> int:
        return sum(f.size for f in self.list_by_ip(ip))

    def entries(self) -> dict[IPAddress, list[FileEntry]]:
        return self._load_db()


class InMemoryFileStore:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._entries: dict[IPAddress, list[FileEntry]] = {}

    def store(self, ip: str, filename: str, data: bytes) -> FileEntry:
        self._files[filename] = data
        entry = FileEntry(filename=filename, size=len(data), time=time.time())
        ip_files = self._entries.get(IPAddress(ip), [])
        ip_files.append(entry)
        self._entries[IPAddress(ip)] = ip_files
        return entry

    def retrieve(self, uuid_name: str) -> bytes | None:
        return self._files.get(uuid_name)

    def delete_by_ip(self, ip: str) -> int:
        ip_files = self._entries.pop(IPAddress(ip), [])
        for entry in ip_files:
            self._files.pop(entry.filename, None)
        return len(ip_files)

    def delete_expired(self, max_age_seconds: float) -> int:
        now = time.time()
        removed = 0
        for ip, files in list(self._entries.items()):
            kept: list[FileEntry] = []
            for entry in files:
                if now - entry.time > max_age_seconds:
                    self._files.pop(entry.filename, None)
                    removed += 1
                else:
                    kept.append(entry)
            if kept:
                self._entries[ip] = kept
            else:
                del self._entries[ip]
        return removed

    def list_by_ip(self, ip: str) -> list[FileEntry]:
        return list(self._entries.get(IPAddress(ip), []))

    def used_bytes(self) -> int:
        return sum(len(d) for d in self._files.values())

    def used_bytes_by_ip(self, ip: str) -> int:
        return sum(f.size for f in self.list_by_ip(ip))

    def entries(self) -> dict[IPAddress, list[FileEntry]]:
        return {ip: list(files) for ip, files in self._entries.items()}
