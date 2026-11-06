from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

IPAddress = NewType("IPAddress", str)


@dataclass(frozen=True)
class Config:
    upload_dir: str
    max_storage_gb: int
    max_age_hours: int
    ip_limit_gb: int
    files_db: str
    rate_limit_seconds: int
    cleanup_interval_seconds: int
    public_base_url: str
    trusted_proxies: tuple[str, ...] = ()
    max_upload_mb: int = 1024
    request_timeout_seconds: int = 30
    max_connections: int = 16
    port: int = 54000


@dataclass(frozen=True)
class FileEntry:
    filename: str
    size: int
    time: float
