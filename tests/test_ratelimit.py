"""Unit tests for the shared TokenBucket rate limiter."""

import time

from pyf.aggregator.ratelimit import TokenBucket


class TestTokenBucket:
    def test_disabled_rate_never_waits(self):
        """A rate of 0 disables limiting; acquire() returns immediately."""
        bucket = TokenBucket(0)
        start = time.monotonic()
        for _ in range(1000):
            bucket.acquire()
        assert time.monotonic() - start < 0.1

    def test_burst_up_to_capacity_is_immediate(self):
        """The bucket starts full, so capacity acquisitions are immediate."""
        bucket = TokenBucket(20)  # capacity == max(1, rate) == 20
        start = time.monotonic()
        for _ in range(20):
            bucket.acquire()
        assert time.monotonic() - start < 0.1

    def test_throttles_beyond_capacity(self):
        """Acquisitions past the initial burst are paced by the average rate."""
        rate = 20
        bucket = TokenBucket(rate)
        # Drain the initial full bucket, then 10 more must be paced at `rate`/s.
        for _ in range(rate):
            bucket.acquire()
        extra = 10
        start = time.monotonic()
        for _ in range(extra):
            bucket.acquire()
        elapsed = time.monotonic() - start
        # 10 tokens at 20/s ~= 0.5s; allow generous slack for scheduling jitter.
        assert elapsed >= extra / rate * 0.8
