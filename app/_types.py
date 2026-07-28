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
    geo_ip_enabled: bool


@dataclass(frozen=True)
class FileEntry:
    filename: str
    size: int
    time: float
