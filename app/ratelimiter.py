from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, interval_seconds: float = 0.0) -> None:
        self._interval = interval_seconds
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> float:
        if self._interval <= 0:
            return 0.0
        now = time.monotonic()
        with self._lock:
            # Only active cooldowns are retained, not every IP seen since startup.
            self._last = {
                key: value for key, value in self._last.items() if now - value < self._interval
            }
            remaining = self._interval - (now - self._last.get(ip, now - self._interval))
            if remaining > 0:
                return remaining
            self._last[ip] = now
            return 0.0

    def allow(self, ip: str) -> bool:
        return self.retry_after(ip) == 0
