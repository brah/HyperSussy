"""Tests for the whale tracker detection engine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.whale_tracker import WhaleTrackerEngine
from hypersussy.models import AssetSnapshot, Position, Trade
from hypersussy.storage.sqlite import SqliteStorage


class _MockReader:
    """Mock ExchangeReader returning canned positions."""

    def __init__(self, positions: list[Position] | None = None) -> None:
        self.positions = positions or []
        self.get_user_positions = AsyncMock(return_value=self.positions)
        self.get_user_twap_slice_fills = AsyncMock(return_value=[])


def _trade(
    coin: str,
    buyer: str,
    seller: str,
    price: float,
    size: float,
    ts: int,
    tid: int,
) -> Trade:
    """Helper to create a test trade.

    Args:
        coin: Asset name.
        buyer: Buyer address.
        seller: Seller address.
        price: Trade price.
        size: Trade size.
        ts: Timestamp in ms.
        tid: Trade ID.

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
        tx_hash=f"0xh{tid}",
        tid=tid,
    )


def _snapshot(coin: str, ts: int, oi_usd: float) -> AssetSnapshot:
    """Helper to create a minimal asset snapshot.

    Args:
        coin: Asset name.
        ts: Timestamp in ms.
        oi_usd: Open interest in USD.

    Returns:
        An AssetSnapshot instance.
    """
    return AssetSnapshot(
        coin=coin,
        timestamp_ms=ts,
        open_interest=oi_usd / 50000.0,
        open_interest_usd=oi_usd,
        mark_price=50000.0,
        oracle_price=50000.0,
        funding_rate=0.0,
        premium=0.0,
        day_volume_usd=0.0,
    )


class TestWhaleTrackerEngine:
    """Tests for WhaleTrackerEngine."""

    @pytest.fixture
    def settings(self) -> HyperSussySettings:
        """Settings with low thresholds for testing."""
        s = HyperSussySettings()
        s.whale_volume_threshold_usd = 100_000.0
        s.whale_volume_lookback_ms = 3_600_000
        s.large_position_oi_pct = 0.05
        s.large_position_min_oi_usd = 0.0
        s.large_position_change_usd = 50_000.0
        s.position_poll_interval_s = 0.0  # Always poll in tests
        s.alert_cooldown_s = 0
        return s

    @pytest.mark.asyncio
    async def test_whale_discovered_on_volume_threshold(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Address is promoted to tracked when volume crosses threshold."""
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # Feed trades totalling > 100K for 0xwhale
        for i in range(3):
            trade = _trade("BTC", "0xwhale", "0xmm", 50000.0, 1.0, 1000 + i, i)
            await engine.on_trade(trade)

        # 3 trades * 50000 * 1 = 150K > 100K threshold
        tracked = await storage.get_tracked_addresses()
        assert "0xwhale" in tracked

    @pytest.mark.asyncio
    async def test_no_promotion_below_threshold(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Address is not promoted if volume below threshold."""
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        trade = _trade("BTC", "0xsmall", "0xmm", 100.0, 1.0, 1000, 1)
        await engine.on_trade(trade)

        tracked = await storage.get_tracked_addresses()
        assert "0xsmall" not in tracked

    @pytest.mark.asyncio
    async def test_large_position_alert(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when whale position exceeds OI threshold."""
        position = Position(
            coin="BTC",
            address="0xwhale",
            size=10.0,
            entry_price=50000.0,
            mark_price=50000.0,
            liquidation_price=40000.0,
            unrealized_pnl=0.0,
            margin_used=100000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=500_000.0,
            timestamp_ms=5000,
        )
        reader = _MockReader(positions=[position])
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # First, promote whale via trades
        for i in range(3):
            await engine.on_trade(
                _trade("BTC", "0xwhale", "0xmm", 50000.0, 1.0, 1000 + i, i)
            )

        # Set OI so position is > 5%
        await engine.on_asset_update(_snapshot("BTC", 5000, 1_000_000.0))

        # tick should poll and detect large position (500K / 1M = 50%)
        alerts = await engine.tick(5000)
        assert len(alerts) >= 1
        assert any(a.alert_type == "whale_position" for a in alerts)

    @pytest.mark.asyncio
    async def test_position_change_alert(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires on significant position change."""
        pos1 = Position(
            coin="ETH",
            address="0xwhale",
            size=100.0,
            entry_price=2000.0,
            mark_price=2000.0,
            liquidation_price=1500.0,
            unrealized_pnl=0.0,
            margin_used=40000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=200_000.0,
            timestamp_ms=5000,
        )
        pos2 = Position(
            coin="ETH",
            address="0xwhale",
            size=200.0,
            entry_price=2000.0,
            mark_price=2000.0,
            liquidation_price=1500.0,
            unrealized_pnl=0.0,
            margin_used=80000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=400_000.0,
            timestamp_ms=10000,
        )

        reader = _MockReader(positions=[pos1])
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # Promote whale (use unique sellers to avoid promoting them)
        for i in range(3):
            await engine.on_trade(
                _trade("ETH", "0xwhale", f"0xmm{i}", 50000.0, 1.0, 1000 + i, i)
            )

        await engine.on_asset_update(_snapshot("ETH", 5000, 100_000_000.0))

        # First poll -- establishes baseline
        await engine.tick(5000)

        # Second poll -- position increased by 200K > 50K threshold
        reader.get_user_positions.return_value = [pos2]
        alerts = await engine.tick(50000)
        change_alerts = [a for a in alerts if a.alert_type == "whale_position_change"]
        assert len(change_alerts) == 1
        assert "increased" in change_alerts[0].title

    @pytest.mark.asyncio
    async def test_tick_fetches_twap_fills_once_per_tracked_address(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """tick() should not duplicate TWAP fetches through position polling."""
        position = Position(
            coin="BTC",
            address="0xwhale",
            size=1.0,
            entry_price=50000.0,
            mark_price=50000.0,
            liquidation_price=40000.0,
            unrealized_pnl=0.0,
            margin_used=10000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=50_000.0,
            timestamp_ms=5000,
        )
        reader = _MockReader(positions=[position])
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        for i in range(3):
            await engine.on_trade(
                _trade("BTC", "0xwhale", f"0xmm{i}", 50_000.0, 1.0, 1000 + i, i)
            )

        await engine.tick(5000)

        assert reader.get_user_twap_slice_fills.await_count == 1

    @pytest.mark.asyncio
    async def test_volume_pruning(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Old volume entries are pruned from the sliding window."""
        settings.whale_volume_lookback_ms = 1000
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # Trade at ts=100
        await engine.on_trade(_trade("BTC", "0xaddr", "0xmm", 50000.0, 1.0, 100, 1))

        # Tick at ts=2000 should prune the trade (100 < 2000-1000)
        await engine.tick(2000)
        assert engine._whale_discovery._address_volume.get("0xaddr") is None

    @pytest.mark.asyncio
    async def test_on_asset_update_tracks_oi(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """on_asset_update caches OI per coin."""
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)
        await engine.on_asset_update(_snapshot("SOL", 1000, 5_000_000.0))
        assert engine._position_tracker._coin_oi["SOL"] == 5_000_000.0

    @pytest.mark.asyncio
    async def test_oi_whale_discovery_blocked_below_min_notional(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """OI-path discovery is skipped when coin volume < whale_oi_min_notional_usd."""
        settings.whale_volume_threshold_usd = 10_000_000.0  # unreachable
        settings.whale_discovery_oi_pct = 0.01  # very low so OI pct passes easily
        settings.whale_oi_min_notional_usd = 500_000.0
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # coin OI = 1M, address trades 20K (2% of OI — above 1% pct, below 500K floor)
        await engine.on_asset_update(_snapshot("BTC", 1000, 1_000_000.0))
        await engine.on_trade(_trade("BTC", "0xsmalloi", "0xmm", 200.0, 100.0, 1000, 1))

        tracked = await storage.get_tracked_addresses()
        assert "0xsmalloi" not in tracked

    @pytest.mark.asyncio
    async def test_oi_whale_discovery_passes_with_sufficient_notional(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """OI-path discovery promotes address when coin volume meets both OI pct and notional floor."""
        settings.whale_volume_threshold_usd = 10_000_000.0  # unreachable
        settings.whale_discovery_oi_pct = 0.01
        settings.whale_oi_min_notional_usd = 500_000.0
        reader = _MockReader()
        engine = WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)

        # coin OI = 1M, address trades 600K (60% of OI — above both thresholds)
        await engine.on_asset_update(_snapshot("BTC", 1000, 1_000_000.0))
        await engine.on_trade(
            _trade("BTC", "0xoiwhale", "0xmm", 60000.0, 10.0, 1000, 1)
        )

        tracked = await storage.get_tracked_addresses()
        assert "0xoiwhale" in tracked
