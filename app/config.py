from __future__ import annotations

import json
import os

from _types import Config


def _config_str(val: object, default: str) -> str:
    return str(val) if val is not None else default


def _config_int(val: object, default: int) -> int:
    return int(val) if val is not None else default


def _config_bool(val: object, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


def load_config(base_dir: str) -> Config:
    config_path = os.path.join(base_dir, "config.json")
    try:
        with open(config_path) as f:
            raw: dict[str, object] = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError("failed to parse config.json") from err
    return Config(
        upload_dir=_config_str(raw.get("UPLOAD_DIR"), "uploads"),
        max_storage_gb=_config_int(raw.get("MAX_STORAGE_GB"), 50),
        max_age_hours=_config_int(raw.get("MAX_AGE_HOURS"), 5),
        ip_limit_gb=_config_int(raw.get("IP_LIMIT_GB"), 10),
        files_db=_config_str(raw.get("FILES_DB"), "data/files_db.json"),
        rate_limit_seconds=_config_int(raw.get("RATE_LIMIT_SECONDS"), 0),
        cleanup_interval_seconds=_config_int(raw.get("CLEANUP_INTERVAL_SECONDS"), 300),
        public_base_url=_config_str(raw.get("PUBLIC_BASE_URL"), ""),
        geo_ip_enabled=_config_bool(raw.get("GEO_IP_ENABLED"), True),
    )
