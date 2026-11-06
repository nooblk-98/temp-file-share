"""Isolated browser-test service; all files are synthetic and ephemeral."""

import dataclasses
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
sys.path.insert(0, str(APP))
from config import load_config  # noqa: E402
from filestore import DiskFileStore  # noqa: E402
from ratelimiter import RateLimiter  # noqa: E402

from app import BoundedThreadingServer, load_templates, make_handler  # noqa: E402

with tempfile.TemporaryDirectory() as root:
    cfg = dataclasses.replace(
        load_config(str(APP)),
        upload_dir=str(Path(root) / "uploads"),
        files_db=str(Path(root) / "data/db.json"),
        public_base_url="http://127.0.0.1:54002",
        trusted_proxies=(),
        rate_limit_seconds=1,
        max_upload_mb=1,
    )
    store = DiskFileStore(cfg.upload_dir, cfg.files_db)
    handler = make_handler(store, RateLimiter(1), load_templates(str(APP)), cfg, str(APP))
    with BoundedThreadingServer(("127.0.0.1", 54002), handler) as server:
        server.serve_forever()
