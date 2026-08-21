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


def _env_or_raw(key: str, raw: dict[str, object]) -> object:
    return os.environ[key] if key in os.environ else raw.get(key)


def load_config(base_dir: str) -> Config:
    config_path = os.path.join(base_dir, "config.json")
    try:
        with open(config_path) as f:
            raw: dict[str, object] = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError("failed to parse config.json") from err
    return Config(
        upload_dir=_config_str(_env_or_raw("UPLOAD_DIR", raw), "uploads"),
        max_storage_gb=_config_int(_env_or_raw("MAX_STORAGE_GB", raw), 50),
        max_age_hours=_config_int(_env_or_raw("MAX_AGE_HOURS", raw), 5),
        ip_limit_gb=_config_int(_env_or_raw("IP_LIMIT_GB", raw), 10),
        files_db=_config_str(_env_or_raw("FILES_DB", raw), "data/files_db.json"),
        rate_limit_seconds=_config_int(_env_or_raw("RATE_LIMIT_SECONDS", raw), 0),
        cleanup_interval_seconds=_config_int(_env_or_raw("CLEANUP_INTERVAL_SECONDS", raw), 300),
        public_base_url=_config_str(_env_or_raw("PUBLIC_BASE_URL", raw), ""),
        geo_ip_enabled=_config_bool(_env_or_raw("GEO_IP_ENABLED", raw), True),
    )
