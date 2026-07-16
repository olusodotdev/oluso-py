from __future__ import annotations

import threading
import time
from typing import Callable, List


class RateLimiter:
    """Caps how many errors are reported within a rolling one-minute window."""

    def __init__(self, max_per_minute: int = 60, now: Callable[[], float] = time.time) -> None:
        self._max_per_minute = max_per_minute if max_per_minute > 0 else 60
        self._now = now
        self._timestamps: List[float] = []
        self._lock = threading.Lock()

    def can_send(self) -> bool:
        with self._lock:
            now = self._now()
            cutoff = now - 60
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

            if len(self._timestamps) < self._max_per_minute:
                self._timestamps.append(now)
                return True
            return False

    def count(self) -> int:
        with self._lock:
            cutoff = self._now() - 60
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]
            return len(self._timestamps)

    def reset(self) -> None:
        with self._lock:
            self._timestamps = []
