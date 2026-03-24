"""Tests for the async rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from hypersussy.rate_limiter import WeightRateLimiter


class TestWeightRateLimiter:
    """Tests for WeightRateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_within_budget(self) -> None:
        """Acquiring weight within budget completes immediately."""
        limiter = WeightRateLimiter(max_weight=100, window_seconds=60)
        start = time.monotonic()
        await limiter.acquire(50)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
        assert limiter.available_weight == 50

    @pytest.mark.asyncio
    async def test_acquire_exceeds_max_raises(self) -> None:
        """Requesting more than max_weight raises ValueError."""
        limiter = WeightRateLimiter(max_weight=100, window_seconds=60)
        with pytest.raises(ValueError, match="exceeds max"):
            await limiter.acquire(101)

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_full(self) -> None:
        """Acquiring blocks until weight frees up."""
        limiter = WeightRateLimiter(max_weight=10, window_seconds=1)
        await limiter.acquire(10)
        assert limiter.available_weight == 0

        # This should block briefly until the window expires
        start = time.monotonic()
        await limiter.acquire(5)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9  # Should wait ~1 second

    @pytest.mark.asyncio
    async def test_used_weight_tracks_correctly(self) -> None:
        """Used weight accumulates with each acquire."""
        limiter = WeightRateLimiter(max_weight=100, window_seconds=60)
        await limiter.acquire(20)
        await limiter.acquire(30)
        assert limiter.used_weight == 50
        assert limiter.available_weight == 50

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self) -> None:
        """Multiple concurrent acquires respect the limit."""
        limiter = WeightRateLimiter(max_weight=50, window_seconds=60)

        async def acquire_chunk(weight: int) -> None:
            await limiter.acquire(weight)

        # Launch 5 concurrent acquires of 10 each = 50 total
        await asyncio.gather(*[acquire_chunk(10) for _ in range(5)])
        assert limiter.used_weight == 50
