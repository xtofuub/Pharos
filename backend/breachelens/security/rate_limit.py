"""Simple in-memory rate limiter (sliding window per key)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._lock = threading.Lock()
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window = 60.0
        with self._lock:
            entries = self._hits[key]
            entries[:] = [t for t in entries if now - t < window]
            if len(entries) >= self.max_per_minute:
                return False
            entries.append(now)
            return True
