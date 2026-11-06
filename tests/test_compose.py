"""Guard the image channels and isolation of the three runnable stacks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is required")
class ComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("HOST_", "DEV_", "SOURCE_", "IMAGE_")) or key in (
                "UPLOADS_HOST_DIR",
                "DATA_HOST_DIR",
                "TRUSTED_PROXIES",
                "PUBLIC_BASE_URL",
            ):
                del env[key]
        cls.configs = {}
        for channel, file in [
            ("stable", "docker-compose.yaml"),
            ("development", "docker-compose.dev.yaml"),
            ("source", "docker-compose.source.yaml"),
        ]:
            raw = subprocess.check_output(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    "/dev/null",
                    "-f",
                    file,
                    "config",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                text=True,
            )
            cls.configs[channel] = json.loads(raw)

    def test_stable_and_development_pull_separate_channels_without_building(self):
        for channel, tag in [("stable", "live"), ("development", "development")]:
            backend = self.configs[channel]["services"]["backend"]
            self.assertEqual(backend["image"], f"ghcr.io/nooblk-98/temp-file-share:{tag}")
            self.assertNotIn("build", backend)

    def test_source_builds_the_shared_dockerfile_locally(self):
        backend = self.configs["source"]["services"]["backend"]
        self.assertEqual(backend["image"], "temp-file-share:source")
        self.assertEqual(Path(backend["build"]["context"]), ROOT / "app")
        self.assertEqual(backend["build"]["dockerfile"], "Dockerfile")

    def test_stacks_do_not_share_project_container_storage_or_default_port(self):
        for selector in [
            lambda c: c["name"],
            lambda c: c["services"]["backend"]["container_name"],
            lambda c: c["services"]["backend"]["ports"][0]["published"],
        ]:
            self.assertEqual(len({selector(c) for c in self.configs.values()}), 3)
        paths = []
        for config in self.configs.values():
            backend = config["services"]["backend"]
            binds = {v["target"]: v["source"] for v in backend["volumes"] if v["type"] == "bind"}
            paths.append((binds["/app/uploads"], binds["/app/data"]))
        self.assertEqual(len(set(paths)), 3)
        self.assertEqual(len({path for pair in paths for path in pair}), 6)

    def test_all_channels_keep_hardening_and_safe_default_proxy_trust(self):
        for config in self.configs.values():
            backend = config["services"]["backend"]
            with self.subTest(project=config["name"]):
                self.assertTrue(backend["read_only"])
                self.assertTrue(backend["init"])
                self.assertEqual(backend["cap_drop"], ["ALL"])
                self.assertIn("no-new-privileges:true", backend["security_opt"])
                self.assertEqual(backend["ports"][0]["host_ip"], "127.0.0.1")
                self.assertEqual(backend["environment"]["TRUSTED_PROXIES"], "")
                self.assertEqual(backend["restart"], "unless-stopped")
