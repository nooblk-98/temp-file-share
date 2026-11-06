#!/usr/bin/env python3
"""Run each real Compose configuration with disposable, isolated storage/ports."""

from __future__ import annotations

import concurrent.futures
import http.client
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
IMAGE = sys.argv[1] if len(sys.argv) > 1 else "temp-file-share:test"


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, cwd=ROOT, stderr=subprocess.STDOUT, **kwargs)


def check(file):
    project = "tfs-check-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        root = Path(directory)
        root.chmod(0o755)
        for name in ["uploads", "data"]:
            (root / name).mkdir()
        run(
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--entrypoint",
            "chown",
            "-v",
            f"{root}:/w",
            IMAGE,
            "-R",
            "10001:10001",
            "/w/uploads",
            "/w/data",
        )
        config = json.loads(
            run(
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                file,
                "config",
                "--format",
                "json",
            )
        )
        config["name"] = project
        backend = config["services"]["backend"]
        backend["container_name"] = project
        backend["image"] = IMAGE
        backend.pop("build", None)
        backend["pull_policy"] = "never"
        backend["ports"] = [
            {"target": 54000, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp"}
        ]
        backend["volumes"] = [
            {"type": "bind", "source": str(root / "uploads"), "target": "/app/uploads"},
            {"type": "bind", "source": str(root / "data"), "target": "/app/data"},
            {"type": "volume", "target": "/tmp"},
        ]
        backend["environment"]["RATE_LIMIT_SECONDS"] = "0"
        backend["environment"]["PUBLIC_BASE_URL"] = "http://localhost"
        backend["environment"]["TRUSTED_PROXIES"] = ""
        config.pop("volumes", None)
        config_path = root / "compose.json"
        config_path.write_text(json.dumps(config))
        command = ["docker", "compose", "-p", project, "-f", str(config_path)]
        try:
            run(*command, "up", "-d", "--pull", "never", "--wait", "--wait-timeout", "60")
            container = json.loads(run("docker", "inspect", project))[0]
            port = int(container["NetworkSettings"]["Ports"]["54000/tcp"][0]["HostPort"])
            payload = os.urandom(65536)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("POST", "/upload", body=payload)
            response = connection.getresponse()
            result = response.read()
            assert response.status == 200, (file, response.status, result)
            path = urlsplit(result.decode().splitlines()[0]).path
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200 and response.read() == payload, file
            connection.close()
            print(f"{file}: healthy; isolated 64 KiB round trip passed", flush=True)
        finally:
            try:
                run(*command, "down", "--volumes", "--remove-orphans")
            finally:
                # Return non-root container-owned fixtures to the test runner.
                run(
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    "--cap-drop",
                    "ALL",
                    "--cap-add",
                    "CHOWN",
                    "--entrypoint",
                    "chown",
                    "-v",
                    f"{root}:/w",
                    IMAGE,
                    "-R",
                    f"{os.getuid()}:{os.getgid()}",
                    "/w",
                )


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(
            pool.map(
                check,
                ["docker-compose.yaml", "docker-compose.dev.yaml", "docker-compose.source.yaml"],
            )
        )
