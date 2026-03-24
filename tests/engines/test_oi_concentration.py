"""Tests for OI concentration detection engine."""

from __future__ import annotations

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.oi_concentration import OiConcentrationEngine
from hypersussy.models import AssetSnapshot, Trade
from hypersussy.storage.sqlite import SqliteStorage


@pytest.fixture
def engine(
    storage: SqliteStorage, settings: HyperSussySettings
) -> OiConcentrationEngine:
    """Create an OI concentration engine for tests."""
    settings.oi_change_pct_threshold = 0.10
    settings.oi_concentration_threshold = 0.20
    settings.oi_min_usd = 1000.0
    settings.alert_cooldown_s = 0  # No cooldown for tests
    return OiConcentrationEngine(storage=storage, settings=settings)


def _snapshot(coin: str, ts: int, oi_usd: float) -> AssetSnapshot:
    """Helper to create a minimal asset snapshot.

    Args:
        coin: Asset name.
        ts: Timestamp in milliseconds.
        oi_usd: Open interest in USD.

    Returns:
        AssetSnapshot with the given values.
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


class TestOiConcentrationEngine:
    """Tests for OiConcentrationEngine."""

    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(
        self,
        engine: OiConcentrationEngine,
        storage: SqliteStorage,
    ) -> None:
        """No alert when OI change is below threshold."""
        # 5% change, below 10% threshold
        await engine.on_asset_update(_snapshot("BTC", 1000, 100_000))
        await engine.on_asset_update(_snapshot("BTC", 301_000, 105_000))
        alerts = await engine.tick(301_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_alert_on_concentrated_oi_spike(
        self,
        engine: OiConcentrationEngine,
        storage: SqliteStorage,
    ) -> None:
        """Alert fires when OI spikes with concentrated trading."""
        # Seed trades from a concentrated address
        trades = [
            Trade(
                coin="BTC",
                price=50000.0,
                size=1.0,
                side="B",
                timestamp_ms=100_000,
                buyer="0xwhale",
                seller="0xmm",
                tx_hash="0xh1",
                tid=i,
            )
            for i in range(10)
        ]
        await storage.insert_trades(trades)

        # OI increases by 20% over the 5m window
        await engine.on_asset_update(_snapshot("BTC", 1000, 100_000))
        await engine.on_asset_update(_snapshot("BTC", 301_000, 120_000))

        alerts = await engine.tick(301_000)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "oi_concentration"
        assert alerts[0].coin == "BTC"
        assert "increased" in alerts[0].title

    @pytest.mark.asyncio
    async def test_no_alert_without_concentration(
        self,
        engine: OiConcentrationEngine,
        storage: SqliteStorage,
    ) -> None:
        """No alert when OI spikes but trading is dispersed."""
        # Many addresses each with small volume
        trades = [
            Trade(
                coin="SOL",
                price=100.0,
                size=1.0,
                side="B",
                timestamp_ms=100_000,
                buyer=f"0xaddr{i}",
                seller=f"0xmm{i}",
                tx_hash=f"0xh{i}",
                tid=i,
            )
            for i in range(100)
        ]
        await storage.insert_trades(trades)

        # OI increases by 15%
        await engine.on_asset_update(_snapshot("SOL", 1000, 10_000))
        await engine.on_asset_update(_snapshot("SOL", 301_000, 11_500))

        alerts = await engine.tick(301_000)
        # With 100 unique addresses, top-5 concentration should be
        # low (~5%), below the 20% threshold
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_ignores_small_coins(
        self,
        engine: OiConcentrationEngine,
    ) -> None:
        """Coins below oi_min_usd are ignored."""
        await engine.on_asset_update(_snapshot("TINY", 1000, 500))
        await engine.on_asset_update(_snapshot("TINY", 301_000, 600))
        alerts = await engine.tick(301_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_on_trade_is_noop(
        self,
        engine: OiConcentrationEngine,
    ) -> None:
        """on_trade returns empty for this engine."""
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
