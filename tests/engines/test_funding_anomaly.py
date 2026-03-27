"""Tests for the funding anomaly detection engine."""

from __future__ import annotations

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.funding_anomaly import FundingAnomalyEngine
from hypersussy.models import AssetSnapshot, Trade


def _snapshot(coin: str, ts: int, funding_rate: float) -> AssetSnapshot:
    """Helper to create a snapshot with a specific funding rate.

    Args:
        coin: Asset name.
        ts: Timestamp in ms.
        funding_rate: Funding rate value.

    Returns:
        An AssetSnapshot instance.
    """
    return AssetSnapshot(
        coin=coin,
        timestamp_ms=ts,
        open_interest=100.0,
        open_interest_usd=5_000_000.0,
        mark_price=50000.0,
        oracle_price=50000.0,
        funding_rate=funding_rate,
        premium=0.0,
        day_volume_usd=0.0,
    )


class TestFundingAnomalyEngine:
    """Tests for FundingAnomalyEngine."""

    @pytest.fixture
    def settings(self) -> HyperSussySettings:
        """Settings for testing."""
        s = HyperSussySettings()
        s.funding_zscore_threshold = 3.0
        s.funding_abs_threshold = 0.001
        s.funding_rolling_window = 168
        s.alert_cooldown_s = 0
        return s

    def _seed_history(
        self,
        engine: FundingAnomalyEngine,
        coin: str,
        rate: float,
        count: int,
    ) -> None:
        """Directly populate the funding history buffer.

        Args:
            engine: Engine instance.
            coin: Asset name.
            rate: Funding rate to repeat.
            count: Number of samples.
        """
        for _ in range(count):
            engine._history[coin].append(rate)

    @pytest.mark.asyncio
    async def test_detects_zscore_anomaly(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when funding z-score exceeds threshold."""
        engine = FundingAnomalyEngine(settings=settings)

        # Seed 50 normal samples at 0.0001
        self._seed_history(engine, "BTC", 0.0001, 50)

        # Current rate is an extreme outlier
        engine._latest_rate["BTC"] = 0.005

        alerts = await engine.tick(100_000)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "funding_anomaly"
        assert alerts[0].coin == "BTC"

    @pytest.mark.asyncio
    async def test_detects_absolute_threshold(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when absolute funding rate exceeds threshold."""
        engine = FundingAnomalyEngine(settings=settings)

        # Seed varied history so z-score alone might not trigger
        for i in range(30):
            engine._history["ETH"].append(0.0005 + i * 0.00001)

        # Absolute rate > 0.001
        engine._latest_rate["ETH"] = 0.002

        alerts = await engine.tick(100_000)
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_no_alert_normal_funding(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when funding is within normal range."""
        engine = FundingAnomalyEngine(settings=settings)

        self._seed_history(engine, "BTC", 0.0001, 50)
        engine._latest_rate["BTC"] = 0.00012  # Slightly above mean, normal

        alerts = await engine.tick(100_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_no_alert_insufficient_samples(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when insufficient data for statistics."""
        engine = FundingAnomalyEngine(settings=settings)

        # Only 5 samples, below _MIN_SAMPLES=24
        self._seed_history(engine, "SOL", 0.0001, 5)
        engine._latest_rate["SOL"] = 0.01

        alerts = await engine.tick(100_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_hourly_sampling(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """on_asset_update only samples once per hour."""
        engine = FundingAnomalyEngine(settings=settings)

        # Two updates 30min apart -- only first should be sampled
        await engine.on_asset_update(_snapshot("BTC", 0, 0.0001))
        await engine.on_asset_update(_snapshot("BTC", 1_800_000, 0.0002))

        assert len(engine._history["BTC"]) == 1

        # Update at 1h should be sampled
        await engine.on_asset_update(_snapshot("BTC", 3_600_000, 0.0003))
        assert len(engine._history["BTC"]) == 2

    @pytest.mark.asyncio
    async def test_on_trade_is_noop(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """on_trade returns empty list."""
        engine = FundingAnomalyEngine(settings=settings)
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
    async def test_negative_funding_anomaly(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires for extreme negative funding."""
        engine = FundingAnomalyEngine(settings=settings)
        self._seed_history(engine, "DOGE", 0.0001, 50)
        engine._latest_rate["DOGE"] = -0.005

        alerts = await engine.tick(100_000)
        assert len(alerts) == 1
