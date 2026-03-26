"""Tests for the liquidation cascade risk engine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.liquidation_risk import (
    LiquidationRiskEngine,
    _compute_impact_ratio,
)
from hypersussy.models import AssetSnapshot, L2Book, Position, Trade
from hypersussy.storage.sqlite import SqliteStorage


class _MockReader:
    """Mock ExchangeReader returning canned L2 book."""

    def __init__(self, book: L2Book | None = None) -> None:
        self.get_l2_book = AsyncMock(return_value=book)
        self.get_user_positions = AsyncMock(return_value=[])


def _book(coin: str, bid_depth: float, ask_depth: float) -> L2Book:
    """Helper to create a simple L2 book.

    Args:
        coin: Asset name.
        bid_depth: Total bid size across levels.
        ask_depth: Total ask size across levels.

    Returns:
        An L2Book instance.
    """
    return L2Book(
        coin=coin,
        timestamp_ms=1000,
        bids=((50000.0, bid_depth),),
        asks=((50100.0, ask_depth),),
    )


class TestComputeImpactRatio:
    """Tests for _compute_impact_ratio."""

    def test_normal_ratio(self) -> None:
        """Impact ratio is position / same-side executable depth."""
        book = _book("BTC", 10.0, 10.0)
        assert _compute_impact_ratio(book, 5.0) == pytest.approx(0.5)

    def test_empty_book(self) -> None:
        """Empty book returns inf."""
        book = L2Book(coin="BTC", timestamp_ms=1000, bids=(), asks=())
        assert _compute_impact_ratio(book, 1.0) == float("inf")

    def test_uses_executable_side_only(self) -> None:
        """Longs should use bids, shorts should use asks."""
        book = _book("BTC", bid_depth=2.0, ask_depth=20.0)
        assert _compute_impact_ratio(book, 4.0) == pytest.approx(2.0)
        assert _compute_impact_ratio(book, -4.0) == pytest.approx(0.2)


class TestLiquidationRiskEngine:
    """Tests for LiquidationRiskEngine."""

    @pytest.fixture
    def settings(self) -> HyperSussySettings:
        """Settings for testing."""
        s = HyperSussySettings()
        s.liquidation_distance_threshold = 0.05
        s.alert_cooldown_s = 0
        return s

    @pytest.mark.asyncio
    async def test_alert_on_near_liquidation(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when whale is close to liquidation."""
        # Setup: tracked whale with position near liquidation
        await storage.upsert_tracked_address(
            "0xwhale", "whale1", "discovered", 1_000_000.0
        )

        pos = Position(
            coin="BTC",
            address="0xwhale",
            size=10.0,
            entry_price=50000.0,
            mark_price=50000.0,
            liquidation_price=49000.0,  # 2% away
            unrealized_pnl=-5000.0,
            margin_used=100000.0,
            leverage_value=10,
            leverage_type="cross",
            notional_usd=500_000.0,
            timestamp_ms=1000,
        )
        await storage.insert_positions([pos])

        book = _book("BTC", 5.0, 5.0)
        reader = _MockReader(book=book)
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )
        engine._mark_prices["BTC"] = 50000.0

        alerts = await engine.tick(5000)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "liquidation_risk"
        assert alerts[0].coin == "BTC"

    @pytest.mark.asyncio
    async def test_no_alert_far_from_liquidation(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when whale is far from liquidation."""
        await storage.upsert_tracked_address("0xsafe", "safe1", "discovered", 500_000.0)

        pos = Position(
            coin="ETH",
            address="0xsafe",
            size=50.0,
            entry_price=2000.0,
            mark_price=2000.0,
            liquidation_price=1000.0,  # 50% away
            unrealized_pnl=0.0,
            margin_used=20000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=100_000.0,
            timestamp_ms=1000,
        )
        await storage.insert_positions([pos])

        reader = _MockReader(book=_book("ETH", 100.0, 100.0))
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )
        engine._mark_prices["ETH"] = 2000.0

        alerts = await engine.tick(5000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_no_alert_without_liquidation_price(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when position has no liquidation price."""
        await storage.upsert_tracked_address(
            "0xnoliq", "noliq1", "discovered", 500_000.0
        )

        pos = Position(
            coin="SOL",
            address="0xnoliq",
            size=100.0,
            entry_price=100.0,
            mark_price=100.0,
            liquidation_price=None,
            unrealized_pnl=0.0,
            margin_used=2000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=10_000.0,
            timestamp_ms=1000,
        )
        await storage.insert_positions([pos])

        reader = _MockReader()
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )

        alerts = await engine.tick(5000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_on_asset_update_caches_price(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """on_asset_update stores mark price."""
        reader = _MockReader()
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )
        snap = AssetSnapshot(
            coin="BTC",
            timestamp_ms=1000,
            open_interest=100.0,
            open_interest_usd=5_000_000.0,
            mark_price=51000.0,
            oracle_price=51000.0,
            funding_rate=0.0,
            premium=0.0,
            day_volume_usd=0.0,
        )
        await engine.on_asset_update(snap)
        assert engine._mark_prices["BTC"] == 51000.0

    @pytest.mark.asyncio
    async def test_on_trade_is_noop(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """on_trade returns empty list."""
        reader = _MockReader()
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )
        trade = Trade(
            coin="BTC",
            price=50000.0,
            size=1.0,
            side="B",
            timestamp_ms=1000,
            buyer="0xabc",
            seller="0xdef",
            tx_hash="0xh",
            tid=1,
        )
        assert await engine.on_trade(trade) == []

    @pytest.mark.asyncio
    async def test_short_position_near_liquidation(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires for short position near liquidation."""
        await storage.upsert_tracked_address(
            "0xshort", "short1", "discovered", 500_000.0
        )

        pos = Position(
            coin="BTC",
            address="0xshort",
            size=-5.0,
            entry_price=50000.0,
            mark_price=50000.0,
            liquidation_price=51500.0,  # 3% above mark
            unrealized_pnl=-5000.0,
            margin_used=50000.0,
            leverage_value=10,
            leverage_type="isolated",
            notional_usd=250_000.0,
            timestamp_ms=1000,
        )
        await storage.insert_positions([pos])

        reader = _MockReader(book=_book("BTC", 10.0, 10.0))
        engine = LiquidationRiskEngine(
            storage=storage, reader=reader, settings=settings
        )
        engine._mark_prices["BTC"] = 50000.0

        alerts = await engine.tick(5000)
        assert len(alerts) == 1
        assert "short" in alerts[0].title
