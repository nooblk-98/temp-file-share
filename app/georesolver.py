from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Protocol


class GeoResolver(Protocol):
    def resolve(self, ip: str) -> str | None: ...


class NullGeoResolver:
    def resolve(self, ip: str) -> str | None:
        return None


class HttpGeoResolver:
    def __init__(self, cache_ttl: float = 300.0) -> None:
        self._cache: dict[str, tuple[str | None, float]] = {}
        self._ttl = cache_ttl

    def resolve(self, ip: str) -> str | None:
        now = time.time()
        cached = self._cache.get(ip)
        if cached is not None and now - cached[1] < self._ttl:
            return cached[0]

        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                data: dict[str, object] = json.loads(resp.read().decode("utf-8"))
            result = str(data.get("countryCode", "")) if data.get("status") == "success" else None
        except (urllib.error.URLError, ValueError, TimeoutError):
            result = None

        self._cache[ip] = (result, time.time())
        return result
