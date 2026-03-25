"""Async token-bucket rate limiter for API weight tracking."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class WeightRateLimiter:
    """Token-bucket rate limiter tracking API weight consumption.

    Uses a deque with a running weight total for O(1) prune and
    weight queries instead of O(N) list scans.

    Args:
        max_weight: Maximum weight allowed per window.
        window_seconds: Duration of the sliding window in seconds.
    """

    def __init__(
        self,
        max_weight: int = 1200,
        window_seconds: int = 60,
    ) -> None:
        self._max_weight = max_weight
        self._window_seconds = window_seconds
        self._requests: deque[tuple[float, int]] = deque()
        self._current_weight: int = 0
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        """Remove expired entries outside the sliding window."""
        cutoff = now - self._window_seconds
        while self._requests and self._requests[0][0] < cutoff:
            _, w = self._requests.popleft()
            self._current_weight -= w

    @property
    def used_weight(self) -> int:
        """Current weight used in the sliding window."""
        self._prune(time.monotonic())
        return self._current_weight

    @property
    def available_weight(self) -> int:
        """Remaining weight available in the current window."""
        return self._max_weight - self.used_weight

    async def acquire(self, weight: int) -> None:
        """Block until the requested weight is available.

        Args:
            weight: The API weight cost of the request.

        Raises:
            ValueError: If weight exceeds max_weight.
        """
        if weight > self._max_weight:
            msg = f"Requested weight {weight} exceeds max {self._max_weight}"
            raise ValueError(msg)

        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)
                if self._current_weight + weight <= self._max_weight:
                    self._requests.append((now, weight))
                    self._current_weight += weight
                    return
                # Calculate wait time until enough weight frees up
                needed = self._current_weight + weight - self._max_weight
                freed = 0
                wait_until = now
                for ts, w in self._requests:
                    freed += w
                    if freed >= needed:
                        wait_until = ts + self._window_seconds
                        break

            sleep_duration = max(0.01, wait_until - time.monotonic())
            await asyncio.sleep(sleep_duration)
