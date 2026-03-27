"""Tests for the PositionCensus component."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.position_census import PositionCensus
from hypersussy.models import Position, Trade


def _trade(
    coin: str,
    buyer: str,
    seller: str,
    price: float = 1000.0,
    size: float = 1.0,
    ts: int = 1000,
) -> Trade:
    """Build a minimal Trade for testing.

    Args:
        coin: Asset name.
        buyer: Buyer address.
        seller: Seller address.
        price: Trade price.
        size: Trade size.
        ts: Timestamp in ms.

    Returns:
        A Trade instance.
    """
    return Trade(
        coin=coin,
        price=price,
        size=size,
        side="B",
        timestamp_ms=ts,
        buyer=buyer,
        seller=seller,
        tx_hash="0xhash",
        tid=1,
    )


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


def _make_census(
    poll_interval: float = 0.0,
    min_volume: float = 1_000.0,
    max_addresses: int = 500,
    batch_size: int = 5,
) -> tuple[PositionCensus, MagicMock, MagicMock]:
    """Create a PositionCensus with mock reader and storage.

    Args:
        poll_interval: Polling interval in seconds.
        min_volume: Minimum volume threshold.
        max_addresses: Maximum tracked addresses.
        batch_size: Batch size per tick.

    Returns:
        Tuple of (census, reader_mock, storage_mock).
    """
    settings = HyperSussySettings(
        census_poll_interval_s=poll_interval,
        census_min_volume_usd=min_volume,
        census_max_addresses=max_addresses,
        census_poll_batch_size=batch_size,
    )
    reader = MagicMock()
    reader.get_user_positions = AsyncMock(return_value=[])
    storage = MagicMock()
    storage.insert_positions = AsyncMock()
    census = PositionCensus(storage=storage, reader=reader, settings=settings)
    return census, reader, storage


class TestOnTrade:
    """Tests for PositionCensus.on_trade volume accumulation."""

    def test_accumulates_volume(self) -> None:
        """Volume is accumulated for both buyer and seller."""
        census, _, _ = _make_census()
        census.on_trade(_trade("BTC", "0xbuyer", "0xseller", price=50_000.0, size=1.0))
        assert census._address_volume["0xbuyer"] == 50_000.0
        assert census._address_volume["0xseller"] == 50_000.0

    def test_empty_address_skipped(self) -> None:
        """Empty buyer/seller strings are not tracked."""
        census, _, _ = _make_census()
        census.on_trade(_trade("BTC", "", "0xseller"))
        assert "" not in census._address_volume

    def test_accumulates_across_trades(self) -> None:
        """Volume accumulates across multiple trades for same address."""
        census, _, _ = _make_census()
        census.on_trade(_trade("BTC", "0xaddr", "0xmm", price=1000.0, size=1.0))
        census.on_trade(_trade("BTC", "0xaddr", "0xmm", price=2000.0, size=1.0))
        assert census._address_volume["0xaddr"] == 3_000.0


class TestPruneVolume:
    """Tests for sliding window volume pruning."""

    def test_prunes_expired_entries(self) -> None:
        """Trades older than lookback window are pruned."""
        census, _, _ = _make_census()
        census._settings.census_volume_lookback_ms = 1000
        census.on_trade(_trade("BTC", "0xaddr", "0xmm", price=100.0, size=1.0, ts=100))
        census.prune_volume(timestamp_ms=2000)
        assert census._address_volume.get("0xaddr") is None

    def test_keeps_recent_entries(self) -> None:
        """Trades within the lookback window are kept."""
        census, _, _ = _make_census()
        census._settings.census_volume_lookback_ms = 5000
        census.on_trade(
            _trade("BTC", "0xaddr", "0xmm", price=100.0, size=1.0, ts=3000)
        )
        census.prune_volume(timestamp_ms=5000)
        assert census._address_volume["0xaddr"] == 100.0


class TestTick:
    """Tests for PositionCensus.tick batch polling."""

    @pytest.mark.asyncio
    async def test_polls_qualifying_addresses(self) -> None:
        """Addresses above min volume and not whales are polled."""
        census, reader, storage = _make_census(min_volume=1_000.0, batch_size=10)
        census.on_trade(
            _trade("BTC", "0xaddr", "0xmm", price=10_000.0, size=1.0, ts=100)
        )
        pos = _position("BTC", "0xaddr", 50_000.0)
        reader.get_user_positions = AsyncMock(return_value=[pos])

        await census.tick(timestamp_ms=1_000, whale_addresses=set())

        # Both buyer and seller qualify; verify 0xaddr was polled
        calls = [c.args[0] for c in reader.get_user_positions.call_args_list]
        assert "0xaddr" in calls
        assert storage.insert_positions.await_count >= 1

    @pytest.mark.asyncio
    async def test_excludes_whale_addresses(self) -> None:
        """Addresses already tracked as whales are excluded."""
        census, reader, _ = _make_census(min_volume=1_000.0)
        census.on_trade(
            _trade("BTC", "0xwhale", "0xmm", price=10_000.0, size=1.0, ts=100)
        )

        await census.tick(
            timestamp_ms=1_000, whale_addresses={"0xwhale", "0xmm"}
        )

        reader.get_user_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_excludes_below_min_volume(self) -> None:
        """Addresses below the volume threshold are not polled."""
        census, reader, _ = _make_census(min_volume=50_000.0)
        census.on_trade(
            _trade("BTC", "0xsmall", "0xmm", price=100.0, size=1.0, ts=100)
        )

        await census.tick(timestamp_ms=1_000, whale_addresses=set())

        reader.get_user_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_poll_interval(self) -> None:
        """Addresses recently polled are skipped until interval elapses."""
        census, reader, _ = _make_census(
            poll_interval=60.0, min_volume=1_000.0, batch_size=10
        )
        census.on_trade(
            _trade("BTC", "0xaddr", "0xmm", price=10_000.0, size=1.0, ts=100)
        )
        # Use timestamps large enough to pass the interval check.
        # _last_polled defaults to 0.0; need now_s >= 60.0 → ts >= 60_000
        t0 = 100_000  # 100s

        # Both 0xaddr and 0xmm qualify; count total calls
        await census.tick(timestamp_ms=t0, whale_addresses=set())
        first_count = reader.get_user_positions.await_count
        assert first_count == 2  # 0xaddr + 0xmm

        # 10s later: both should be skipped (interval=60s)
        await census.tick(timestamp_ms=t0 + 10_000, whale_addresses=set())
        assert reader.get_user_positions.await_count == first_count

        # 61s later: both should poll again
        await census.tick(timestamp_ms=t0 + 61_000, whale_addresses=set())
        assert reader.get_user_positions.await_count == first_count * 2

    @pytest.mark.asyncio
    async def test_batch_size_limits(self) -> None:
        """Only batch_size addresses are polled per tick."""
        census, reader, _ = _make_census(batch_size=2, min_volume=1_000.0)
        for i in range(5):
            census.on_trade(
                _trade(
                    "BTC", f"0xaddr{i}", "0xmm",
                    price=10_000.0, size=1.0, ts=100 + i,
                )
            )

        await census.tick(timestamp_ms=1_000, whale_addresses=set())

        assert reader.get_user_positions.await_count == 2

    @pytest.mark.asyncio
    async def test_polls_highest_volume_first(self) -> None:
        """Highest-volume addresses are selected first."""
        census, reader, _ = _make_census(batch_size=1, min_volume=1_000.0)
        # Use same counterparty so 0xmm accumulates most volume
        # but exclude 0xmm as whale to test ranking of 0xsmall vs 0xbig
        census.on_trade(
            _trade("BTC", "0xsmall", "0xmm", price=5_000.0, size=1.0, ts=100)
        )
        census.on_trade(
            _trade("BTC", "0xbig", "0xmm", price=50_000.0, size=1.0, ts=200)
        )

        # Exclude 0xmm (highest volume) to test ranking among the rest
        await census.tick(timestamp_ms=1_000, whale_addresses={"0xmm"})

        reader.get_user_positions.assert_called_once_with(
            "0xbig", active_dexes=set()
        )

    @pytest.mark.asyncio
    async def test_no_insert_for_empty_positions(self) -> None:
        """No storage call when positions list is empty."""
        census, reader, storage = _make_census(min_volume=1_000.0)
        reader.get_user_positions = AsyncMock(return_value=[])
        census.on_trade(
            _trade("BTC", "0xaddr", "0xmm", price=10_000.0, size=1.0, ts=100)
        )

        await census.tick(timestamp_ms=1_000, whale_addresses=set())

        storage.insert_positions.assert_not_called()


class TestEviction:
    """Tests for memory cap enforcement."""

    def test_evicts_lowest_volume(self) -> None:
        """When over max_addresses, lowest-volume addresses are evicted."""
        census, _, _ = _make_census(max_addresses=2)
        census.on_trade(
            _trade("BTC", "0xlow", "0xmm", price=100.0, size=1.0, ts=100)
        )
        census.on_trade(
            _trade("BTC", "0xmed", "0xmm", price=500.0, size=1.0, ts=200)
        )
        census.on_trade(
            _trade("BTC", "0xhigh", "0xmm", price=1000.0, size=1.0, ts=300)
        )
        # 0xmm also has accumulated volume, so we have 4 addresses
        # eviction triggers when > max_addresses * 2 = 4, need one more
        census.on_trade(
            _trade("BTC", "0xextra", "0xmm2", price=50.0, size=1.0, ts=400)
        )
        # Now 5 unique addresses (0xlow, 0xmed, 0xhigh, 0xmm, 0xextra, 0xmm2)
        # That's 6 > 2*2=4, so eviction should fire
        assert len(census._address_volume) <= 2
