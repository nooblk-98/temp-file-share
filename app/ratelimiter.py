from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, interval_seconds: float = 0.0) -> None:
        self._interval = interval_seconds
        self._last: dict[str, float] = {}

    def allow(self, ip: str) -> bool:
        if self._interval <= 0:
            return True
        now = time.time()
        last = self._last.get(ip, 0.0)
        if now - last < self._interval:
            return False
        self._last[ip] = now
        return True
