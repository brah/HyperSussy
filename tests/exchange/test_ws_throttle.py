"""Tests for the WsThrottle WebSocket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from hypersussy.exchange.hyperliquid.websocket import WsThrottle


class TestWsThrottle:
    """Tests for WsThrottle pacing."""

    def test_default_values(self) -> None:
        """Default delays match documented HL-safe values."""
        throttle = WsThrottle()
        assert throttle.connect_delay_s == 2.5
        assert throttle.subscribe_delay_s == 0.05

    @pytest.mark.asyncio
    async def test_wait_connect_enforces_minimum_delay(self) -> None:
        """Second connect waits at least connect_delay_s."""
        throttle = WsThrottle(connect_delay_s=0.1, subscribe_delay_s=0.0)
        await throttle.wait_connect()
        start = time.monotonic()
        await throttle.wait_connect()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09  # Allow small float tolerance

    @pytest.mark.asyncio
    async def test_wait_subscribe_enforces_minimum_delay(self) -> None:
        """Second subscribe waits at least subscribe_delay_s."""
        throttle = WsThrottle(connect_delay_s=0.0, subscribe_delay_s=0.1)
        await throttle.wait_subscribe()
        start = time.monotonic()
        await throttle.wait_subscribe()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09

    @pytest.mark.asyncio
    async def test_concurrent_connects_are_serialized(self) -> None:
        """Three concurrent connects space out by connect_delay_s each."""
        throttle = WsThrottle(connect_delay_s=0.1, subscribe_delay_s=0.0)
        start = time.monotonic()
        await asyncio.gather(
            throttle.wait_connect(),
            throttle.wait_connect(),
            throttle.wait_connect(),
        )
        elapsed = time.monotonic() - start
        # First is instant, 2nd waits 0.1s, 3rd waits 0.2s total
        assert elapsed >= 0.19
