"""Tests for WhaleTrackerEngine.on_position_update (WS push path)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.whale_tracker import WhaleTrackerEngine
from hypersussy.models import Position


def _make_position(
    coin: str = "BTC",
    address: str = "0xwhale",
    notional: float = 10_000_000.0,
) -> Position:
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


def _make_engine() -> tuple[WhaleTrackerEngine, MagicMock]:
    """Create an engine with an AsyncMock storage and seed OI.

    Returns:
        Tuple of (engine, storage_mock).
    """
    storage = MagicMock()
    storage.insert_positions = AsyncMock()
    storage.get_tracked_addresses = AsyncMock(return_value=[])
    storage.upsert_tracked_address = AsyncMock()
    reader = MagicMock()
    reader.get_user_positions = AsyncMock(return_value=[])
    reader.get_user_twap_slice_fills = AsyncMock(return_value=[])

    settings = HyperSussySettings(
        large_position_oi_pct=0.20,
        large_position_change_usd=1_000_000.0,
        alert_cooldown_s=0,
    )
    engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)
    # Seed OI so position-vs-OI alerts can fire
    engine._position_tracker._coin_oi["BTC"] = 50_000_000.0
    return engine, storage


class TestOnPositionUpdateAlerts:
    """Tests for alert generation in on_position_update."""

    @pytest.mark.asyncio
    async def test_fires_large_position_alert(self) -> None:
        """A position ≥ large_position_oi_pct of OI fires a whale_position alert."""
        engine, _ = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=15_000_000.0)  # 30% of OI

        alerts = await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)

        types = [a.alert_type for a in alerts]
        assert "whale_position" in types

    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(self) -> None:
        """A position below the OI threshold does not fire."""
        engine, _ = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=1_000_000.0)  # 2% of OI

        alerts = await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)

        assert not alerts

    @pytest.mark.asyncio
    async def test_fires_change_alert_on_second_call(self) -> None:
        """A significant notional change on second update fires a change alert."""
        engine, _ = _make_engine()
        addr = "0xwhale"

        # First call: seeds _last_positions and _polled_once
        pos1 = _make_position("BTC", addr, notional=5_000_000.0)
        await engine.on_position_update(addr, [pos1], timestamp_ms=1_000)

        # Second call: large change
        pos2 = _make_position("BTC", addr, notional=8_000_000.0)
        alerts = await engine.on_position_update(addr, [pos2], timestamp_ms=2_000)

        types = [a.alert_type for a in alerts]
        assert "whale_position_change" in types

    @pytest.mark.asyncio
    async def test_updates_last_positions(self) -> None:
        """on_position_update updates _last_positions after each call."""
        engine, _ = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=5_000_000.0)

        await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)

        stored = dict(engine._position_tracker._last_positions["0xwhale"])
        assert stored["BTC"] == pytest.approx(5_000_000.0)

    @pytest.mark.asyncio
    async def test_marks_polled_once(self) -> None:
        """Address is added to _polled_once after first on_position_update."""
        engine, _ = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=1_000.0)

        assert "0xwhale" not in engine._position_tracker._polled_once
        await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)
        assert "0xwhale" in engine._position_tracker._polled_once

    @pytest.mark.asyncio
    async def test_inserts_positions_to_storage(self) -> None:
        """Non-empty positions are persisted via storage.insert_positions."""
        engine, storage = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=5_000_000.0)

        await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)

        storage.insert_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_update_last_polled(self) -> None:
        """on_position_update must NOT update _last_polled.

        REST safety-net cadence is independent of the WS push path.
        """
        engine, _ = _make_engine()
        pos = _make_position("BTC", "0xwhale", notional=1_000.0)

        await engine.on_position_update("0xwhale", [pos], timestamp_ms=1_000)

        assert "0xwhale" not in engine._position_tracker._last_polled

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_duplicate_alert(self) -> None:
        """Alert cooldown prevents the same alert firing twice in a row."""
        settings = HyperSussySettings(
            large_position_oi_pct=0.20,
            large_position_change_usd=1_000_000.0,
            alert_cooldown_s=3600,
        )
        storage = MagicMock()
        storage.insert_positions = AsyncMock()
        storage.get_tracked_addresses = AsyncMock(return_value=[])
        storage.upsert_tracked_address = AsyncMock()
        reader = MagicMock()
        reader.get_user_positions = AsyncMock(return_value=[])
        reader.get_user_twap_slice_fills = AsyncMock(return_value=[])

        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)
        engine._position_tracker._coin_oi["BTC"] = 50_000_000.0

        addr = "0xwhale"
        pos = _make_position("BTC", addr, notional=15_000_000.0)

        t0 = 1_700_000_000_000  # realistic ms timestamp
        alerts1 = await engine.on_position_update(addr, [pos], timestamp_ms=t0)
        alerts2 = await engine.on_position_update(addr, [pos], timestamp_ms=t0 + 1_000)

        assert any(a.alert_type == "whale_position" for a in alerts1)
        assert not any(a.alert_type == "whale_position" for a in alerts2)
