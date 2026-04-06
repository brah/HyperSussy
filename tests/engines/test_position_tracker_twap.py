"""Tests for TWAP fill fetching piggybacked on position polling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.position_tracker import PositionTracker
from hypersussy.engines.twap_detector import TwapDetector
from hypersussy.exchange.hyperliquid.client import PositionFetchRateLimitError
from hypersussy.models import Position


def _position(coin: str, address: str, notional: float) -> Position:
    """Build a minimal Position for testing.

    Args:
        coin: Asset name.
        address: Wallet address.
        notional: Notional USD value.

    Returns:
        A Position instance.
    """
    return Position(
        coin=coin,
        address=address,
        size=notional / 50_000.0,
        entry_price=50_000.0,
        mark_price=50_000.0,
        notional_usd=notional,
        unrealized_pnl=0.0,
        margin_used=notional / 5.0,
        liquidation_price=40_000.0,
        leverage_type="cross",
        leverage_value=5,
        timestamp_ms=1_000,
    )


def _make_tracker(
    twap_fills: list[dict] | None = None,
    poll_interval_s: float = 0.0,
) -> tuple[PositionTracker, MagicMock, MagicMock]:
    """Create a PositionTracker with TWAP detector and mock reader.

    Args:
        twap_fills: Canned TWAP fills to return from the mock reader.
        poll_interval_s: Position poll interval in seconds.

    Returns:
        Tuple of (tracker, reader_mock, storage_mock).
    """
    settings = HyperSussySettings(
        position_poll_interval_s=poll_interval_s,
        alert_cooldown_s=0,
        large_position_oi_pct=0.99,
        large_position_change_usd=999_999_999.0,
    )
    reader = MagicMock()
    reader.get_user_positions = AsyncMock(return_value=[])
    reader.get_user_twap_slice_fills = AsyncMock(return_value=twap_fills or [])
    storage = MagicMock()
    storage.insert_positions = AsyncMock()
    twap_detector = TwapDetector(settings)

    tracker = PositionTracker(
        storage=storage,
        reader=reader,
        settings=settings,
        twap_detector=twap_detector,
    )
    return tracker, reader, storage


class TestTwapPiggybacking:
    """Tests for TWAP fills being fetched alongside positions."""

    @pytest.mark.asyncio
    async def test_twap_fetched_for_each_polled_address(self) -> None:
        """TWAP fills are fetched for every address in the poll batch."""
        tracker, reader, _ = _make_tracker()
        pos = _position("BTC", "0xaddr1", 50_000.0)
        reader.get_user_positions = AsyncMock(return_value=[pos])

        await tracker.poll_positions(
            timestamp_ms=1_000, db_tracked={"0xaddr1", "0xaddr2"}
        )

        assert reader.get_user_twap_slice_fills.await_count == 2

    @pytest.mark.asyncio
    async def test_twap_not_fetched_without_detector(self) -> None:
        """Without a TwapDetector, TWAP fills are not fetched."""
        settings = HyperSussySettings(position_poll_interval_s=0.0)
        reader = MagicMock()
        reader.get_user_positions = AsyncMock(return_value=[])
        reader.get_user_twap_slice_fills = AsyncMock(return_value=[])
        storage = MagicMock()
        storage.insert_positions = AsyncMock()

        tracker = PositionTracker(
            storage=storage, reader=reader, settings=settings, twap_detector=None
        )
        await tracker.poll_positions(
            timestamp_ms=1_000, db_tracked={"0xaddr1"}
        )

        reader.get_user_twap_slice_fills.assert_not_called()

    @pytest.mark.asyncio
    async def test_twap_alerts_included_in_result(self) -> None:
        """TWAP alerts are returned alongside position alerts."""
        now_ms = 1_000_000
        twap_fills = [
            {
                "twapId": 42,
                "fill": {
                    "coin": "BTC",
                    "side": "B",
                    "sz": "1.0",
                    "px": "50000.0",
                    "time": now_ms - 100,
                },
            }
        ]
        # poll_interval_s=10 gives active_window = 10*1000*3 = 30_000ms
        tracker, reader, _ = _make_tracker(
            twap_fills=twap_fills, poll_interval_s=10.0
        )

        alerts = await tracker.poll_positions(
            timestamp_ms=now_ms, db_tracked={"0xwhale"}
        )

        twap_alerts = [a for a in alerts if a.alert_type == "twap_detected"]
        assert len(twap_alerts) == 1
        assert twap_alerts[0].coin == "BTC"

    @pytest.mark.asyncio
    async def test_twap_gated_by_poll_interval(self) -> None:
        """TWAP is only fetched when positions are polled (interval-gated)."""
        settings = HyperSussySettings(
            position_poll_interval_s=60.0,
            alert_cooldown_s=0,
        )
        reader = MagicMock()
        reader.get_user_positions = AsyncMock(return_value=[])
        reader.get_user_twap_slice_fills = AsyncMock(return_value=[])
        storage = MagicMock()
        storage.insert_positions = AsyncMock()
        twap_detector = TwapDetector(settings)

        tracker = PositionTracker(
            storage=storage, reader=reader, settings=settings,
            twap_detector=twap_detector,
        )

        # Use timestamps large enough to pass the interval check.
        # _last_polled defaults to 0.0; need now_s >= 60.0 → ts >= 60_000
        t0 = 100_000  # 100s

        # First poll: should fetch
        await tracker.poll_positions(
            timestamp_ms=t0, db_tracked={"0xaddr"}
        )
        assert reader.get_user_twap_slice_fills.await_count == 1

        # 10s later: should NOT fetch (interval=60s)
        await tracker.poll_positions(
            timestamp_ms=t0 + 10_000, db_tracked={"0xaddr"}
        )
        assert reader.get_user_twap_slice_fills.await_count == 1

        # 61s later: should fetch again
        await tracker.poll_positions(
            timestamp_ms=t0 + 61_000, db_tracked={"0xaddr"}
        )
        assert reader.get_user_twap_slice_fills.await_count == 2

    @pytest.mark.asyncio
    async def test_rate_limited_position_fetch_marks_address_polled(self) -> None:
        """Rate-limited address fetches back off instead of retrying immediately."""
        tracker, reader, storage = _make_tracker()
        reader.get_user_positions = AsyncMock(
            side_effect=PositionFetchRateLimitError("0xaddr1", ["xyz"])
        )

        await tracker.poll_positions(
            timestamp_ms=1_000,
            db_tracked={"0xaddr1"},
        )

        assert "0xaddr1" in tracker._last_polled
        storage.insert_positions.assert_not_called()
