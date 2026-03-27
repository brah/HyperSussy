"""Tests for dex-aware position polling in WhaleTrackerEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.whale_tracker import WhaleTrackerEngine
from hypersussy.models import Trade
from hypersussy.storage.sqlite import SqliteStorage


def _trade(coin: str, buyer: str, seller: str, ts: int = 1000) -> Trade:
    """Build a minimal Trade for testing.

    Args:
        coin: Asset name (e.g. "BTC" or "xyz:GOLD").
        buyer: Buyer address.
        seller: Seller address.
        ts: Timestamp in ms.

    Returns:
        A Trade instance.
    """
    return Trade(
        coin=coin,
        price=1000.0,
        size=1.0,
        side="B",
        timestamp_ms=ts,
        buyer=buyer,
        seller=seller,
        tx_hash="0xhash",
        tid=1,
    )


def _make_engine() -> WhaleTrackerEngine:
    """Create an engine with a mock reader and in-memory storage."""
    reader = AsyncMock()
    reader.get_user_positions = AsyncMock(return_value=[])
    reader.get_user_twap_slice_fills = AsyncMock(return_value=[])
    storage = AsyncMock(spec=SqliteStorage)
    storage.get_tracked_addresses = AsyncMock(return_value=[])
    storage.upsert_tracked_address = AsyncMock()
    return WhaleTrackerEngine(
        storage=storage,
        reader=reader,
        settings=HyperSussySettings(),
    )


class TestWhaleActiveDexesPopulation:
    """Tests for _whale_active_dexes population via on_trade."""

    @pytest.mark.asyncio
    async def test_hip3_trade_records_dex_prefix(self) -> None:
        """A trade on 'xyz:GOLD' records dex prefix 'xyz' for both parties."""
        engine = _make_engine()
        await engine.on_trade(_trade("xyz:GOLD", "0xbuyer", "0xseller"))

        assert engine._whale_active_dexes.get("0xbuyer") == {"xyz"}
        assert engine._whale_active_dexes.get("0xseller") == {"xyz"}

    @pytest.mark.asyncio
    async def test_native_trade_no_prefix_recorded(self) -> None:
        """A native (non-HIP-3) trade does not populate _whale_active_dexes."""
        engine = _make_engine()
        await engine.on_trade(_trade("BTC", "0xbuyer", "0xseller"))

        assert "0xbuyer" not in engine._whale_active_dexes
        assert "0xseller" not in engine._whale_active_dexes

    @pytest.mark.asyncio
    async def test_multiple_dexes_accumulated(self) -> None:
        """Trading on two HIP-3 dexes accumulates both prefixes."""
        engine = _make_engine()
        await engine.on_trade(_trade("xyz:GOLD", "0xwhale", "0xother", ts=1000))
        await engine.on_trade(_trade("flx:OIL", "0xwhale", "0xother2", ts=2000))

        assert engine._whale_active_dexes["0xwhale"] == {"xyz", "flx"}

    @pytest.mark.asyncio
    async def test_empty_address_skipped(self) -> None:
        """Empty buyer/seller strings are not added to active dexes."""
        engine = _make_engine()
        await engine.on_trade(_trade("xyz:GOLD", "", ""))

        assert engine._whale_active_dexes == {}


class TestActiveDexesPassedToReader:
    """Tests that active_dexes is forwarded to get_user_positions."""

    @pytest.mark.asyncio
    async def test_none_for_new_whale(self) -> None:
        """New whale with no observed trades passes active_dexes=None."""
        engine = _make_engine()
        addr = "0xnewwhale"

        storage = AsyncMock(spec=SqliteStorage)
        storage.get_tracked_addresses = AsyncMock(return_value=[addr])
        storage.upsert_tracked_address = AsyncMock()
        storage.insert_positions = AsyncMock()
        engine._storage = storage
        # Stamp last poll as expired
        engine._position_tracker._last_polled[addr] = 0.0

        await engine.tick(timestamp_ms=1_000_000)

        engine._reader.get_user_positions.assert_called_once_with(
            addr, active_dexes=None
        )

    @pytest.mark.asyncio
    async def test_dex_set_passed_after_hip3_trade(self) -> None:
        """After observing 'xyz:GOLD', active_dexes={'xyz'} is forwarded."""
        engine = _make_engine()
        addr = "0xwhale"
        await engine.on_trade(_trade("xyz:GOLD", addr, "0xother"))

        storage = AsyncMock(spec=SqliteStorage)
        storage.get_tracked_addresses = AsyncMock(return_value=[addr])
        storage.upsert_tracked_address = AsyncMock()
        storage.insert_positions = AsyncMock()
        engine._storage = storage
        engine._position_tracker._last_polled[addr] = 0.0

        await engine.tick(timestamp_ms=1_000_000)

        engine._reader.get_user_positions.assert_called_once_with(
            addr, active_dexes={"xyz"}
        )
