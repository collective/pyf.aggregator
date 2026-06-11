"""Shared throughput primitives for the aggregator fetchers."""

import threading
import time


class TokenBucket:
    """Thread-safe average-rate limiter that does not serialize concurrency.

    Unlike a fixed inter-request delay, a token bucket lets many requests run
    at once as long as their average rate stays under ``rate_per_sec``. A rate
    of 0 (or less) disables limiting entirely.
    """

    def __init__(self, rate_per_sec):
        self._rate = float(rate_per_sec)
        self._capacity = max(1.0, self._rate)
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        if self._rate <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._last) * self._rate
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            time.sleep(wait)
