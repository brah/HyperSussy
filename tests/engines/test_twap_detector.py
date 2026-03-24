"""Tests for the TWAP detection engine."""

from __future__ import annotations

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.twap_detector import TwapDetectorEngine, _cv
from hypersussy.models import Trade


def _trade(
    buyer: str,
    seller: str,
    coin: str,
    size: float,
    ts: int,
    tid: int,
) -> Trade:
    """Helper to create a test trade.

    Args:
        buyer: Buyer address.
        seller: Seller address.
        coin: Asset name.
        size: Trade size.
        ts: Timestamp in ms.
        tid: Trade ID.

    Returns:
        A Trade instance.
    """
    return Trade(
        coin=coin,
        price=50000.0,
        size=size,
        side="B",
        timestamp_ms=ts,
        buyer=buyer,
        seller=seller,
        tx_hash=f"0xh{tid}",
        tid=tid,
    )


class TestCoefficientOfVariation:
    """Tests for the _cv helper function."""

    def test_identical_values(self) -> None:
        """CV of identical values is 0."""
        assert _cv([1.0, 1.0, 1.0, 1.0]) == 0.0

    def test_single_value_returns_inf(self) -> None:
        """CV of a single value is inf."""
        assert _cv([5.0]) == float("inf")

    def test_normal_variance(self) -> None:
        """CV of varied values is positive and finite."""
        cv = _cv([1.0, 2.0, 3.0, 4.0, 5.0])
        assert 0 < cv < 1


class TestTwapDetectorEngine:
    """Tests for TwapDetectorEngine."""

    @pytest.fixture
    def settings(self) -> HyperSussySettings:
        """Settings with low thresholds for testing."""
        s = HyperSussySettings()
        s.twap_min_fills = 5
        s.twap_max_time_cv = 0.5
        s.twap_max_size_cv = 0.5
        s.twap_window_ms = 600_000  # 10min
        s.twap_min_notional_usd = 0.0  # Disable notional filter for tests
        s.alert_cooldown_s = 0
        return s

    @pytest.mark.asyncio
    async def test_detects_uniform_fills(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Regular fills at even intervals with uniform size trigger alert."""
        engine = TwapDetectorEngine(settings=settings)

        # 10 evenly-spaced fills of identical size
        for i in range(10):
            trade = _trade("0xtwap", "0xmm", "BTC", 1.0, 10000 + i * 60000, i)
            await engine.on_trade(trade)

        alerts = await engine.tick(610000)
        assert len(alerts) >= 1
        assert alerts[0].alert_type == "twap_detected"
        assert "0xtwap" in alerts[0].description

    @pytest.mark.asyncio
    async def test_no_alert_for_irregular_fills(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Highly irregular fill timing does not trigger alert."""
        engine = TwapDetectorEngine(settings=settings)
        settings.twap_max_time_cv = 0.3  # Strict

        # Irregular timestamps
        timestamps = [
            1000,
            2000,
            50000,
            51000,
            200000,
            201000,
            300000,
            400000,
            500000,
            550000,
        ]
        for i, ts in enumerate(timestamps):
            await engine.on_trade(_trade("0xrandom", "0xmm", "ETH", 1.0, ts, i))

        alerts = await engine.tick(600000)
        # With high time CV, should not fire
        twap_alerts = [
            a
            for a in alerts
            if a.alert_type == "twap_detected" and "0xrandom" in a.description
        ]
        assert len(twap_alerts) == 0

    @pytest.mark.asyncio
    async def test_no_alert_below_min_fills(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Too few fills does not trigger alert."""
        engine = TwapDetectorEngine(settings=settings)

        # Only 3 fills, below min_fills=5
        for i in range(3):
            await engine.on_trade(
                _trade("0xfew", "0xmm", "SOL", 1.0, 1000 + i * 60000, i)
            )

        alerts = await engine.tick(200000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_old_fills_pruned(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Fills outside the window are pruned and don't count."""
        settings.twap_window_ms = 100_000
        engine = TwapDetectorEngine(settings=settings)

        # 10 fills all at ts=1000 (will be pruned at tick ts=200000)
        for i in range(10):
            await engine.on_trade(_trade("0xold", "0xmm", "BTC", 1.0, 1000 + i, i))

        alerts = await engine.tick(200_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_tracks_buyer_and_seller_separately(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Buyer and seller fills tracked independently."""
        engine = TwapDetectorEngine(settings=settings)

        # 0xalice is buyer in all trades, 0xbob is seller
        for i in range(10):
            await engine.on_trade(
                _trade("0xalice", "0xbob", "BTC", 1.0, 10000 + i * 60000, i)
            )

        alerts = await engine.tick(610000)
        # Both buyer and seller should be detected as TWAP
        alice_alerts = [a for a in alerts if "0xalice" in a.description]
        bob_alerts = [a for a in alerts if "0xbob" in a.description]
        assert len(alice_alerts) >= 1
        assert len(bob_alerts) >= 1

    @pytest.mark.asyncio
    async def test_on_asset_update_is_noop(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """on_asset_update returns empty list."""
        from hypersussy.models import AssetSnapshot

        engine = TwapDetectorEngine(settings=settings)
        snap = AssetSnapshot(
            coin="BTC",
            timestamp_ms=1000,
            open_interest=100.0,
            open_interest_usd=5_000_000.0,
            mark_price=50000.0,
            oracle_price=50000.0,
            funding_rate=0.0,
            premium=0.0,
            day_volume_usd=0.0,
        )
        result = await engine.on_asset_update(snap)
        assert result == []
