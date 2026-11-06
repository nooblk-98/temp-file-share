from __future__ import annotations

import ipaddress
import json
import os

from models import Config


def _config_str(val: object, default: str) -> str:
    return str(val) if val is not None else default


def _config_int(val: object, default: int) -> int:
    return int(val) if val is not None else default


def _env_or_raw(key: str, raw: dict[str, object]) -> object:
    return os.environ[key] if key in os.environ else raw.get(key)


def load_config(base_dir: str) -> Config:
    config_path = os.path.join(base_dir, "config.json")
    try:
        with open(config_path) as f:
            raw: dict[str, object] = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError("failed to parse config.json") from err
    cfg = Config(
        upload_dir=_config_str(_env_or_raw("UPLOAD_DIR", raw), "uploads"),
        max_storage_gb=_config_int(_env_or_raw("MAX_STORAGE_GB", raw), 50),
        max_age_hours=_config_int(_env_or_raw("MAX_AGE_HOURS", raw), 5),
        ip_limit_gb=_config_int(_env_or_raw("IP_LIMIT_GB", raw), 10),
        files_db=_config_str(_env_or_raw("FILES_DB", raw), "data/files_db.json"),
        rate_limit_seconds=_config_int(_env_or_raw("RATE_LIMIT_SECONDS", raw), 0),
        cleanup_interval_seconds=_config_int(_env_or_raw("CLEANUP_INTERVAL_SECONDS", raw), 300),
        public_base_url=_config_str(_env_or_raw("PUBLIC_BASE_URL", raw), ""),
        trusted_proxies=tuple(
            x.strip()
            for x in _config_str(_env_or_raw("TRUSTED_PROXIES", raw), "").split(",")
            if x.strip()
        ),
        max_upload_mb=_config_int(_env_or_raw("MAX_UPLOAD_MB", raw), 1024),
        request_timeout_seconds=_config_int(_env_or_raw("REQUEST_TIMEOUT_SECONDS", raw), 30),
        max_connections=_config_int(_env_or_raw("MAX_CONNECTIONS", raw), 16),
        port=_config_int(_env_or_raw("PORT", raw), 54000),
    )

    for name in (
        "max_storage_gb",
        "max_age_hours",
        "ip_limit_gb",
        "max_upload_mb",
        "cleanup_interval_seconds",
        "request_timeout_seconds",
        "max_connections",
    ):
        if getattr(cfg, name) <= 0:
            raise ValueError(f"{name} must be positive")
    if cfg.rate_limit_seconds < 0 or not 1 <= cfg.port <= 65535:
        raise ValueError("invalid rate limit or port")
    for network in cfg.trusted_proxies:
        ipaddress.ip_network(network, strict=False)
    if cfg.public_base_url:
        from urllib.parse import urlsplit

        parsed = urlsplit(cfg.public_base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("PUBLIC_BASE_URL must be an http(s) base URL")
    return cfg
