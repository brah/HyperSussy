"""Tests for the pre-move correlation engine."""

from __future__ import annotations

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.engines.pre_move import PreMoveEngine
from hypersussy.models import AssetSnapshot, Trade


def _snapshot(coin: str, ts: int, price: float) -> AssetSnapshot:
    """Helper to create a minimal asset snapshot.

    Args:
        coin: Asset name.
        ts: Timestamp in ms.
        price: Mark price.

    Returns:
        An AssetSnapshot instance.
    """
    return AssetSnapshot(
        coin=coin,
        timestamp_ms=ts,
        open_interest=100.0,
        open_interest_usd=5_000_000.0,
        mark_price=price,
        oracle_price=price,
        funding_rate=0.0,
        premium=0.0,
        day_volume_usd=0.0,
    )


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


class TestPreMoveEngine:
    """Tests for PreMoveEngine."""

    @pytest.fixture
    def settings(self) -> HyperSussySettings:
        """Settings with low thresholds for testing."""
        s = HyperSussySettings()
        s.pre_move_threshold_pct = 0.02  # 2%
        s.pre_move_windows_ms = [60_000]  # 1min
        s.pre_move_lookback_ms = 60_000  # 1min lookback
        s.pre_move_min_notional_usd = 10_000.0
        s.pre_move_top_n = 3
        s.pre_move_cooldown_ms = 0
        return s

    @pytest.mark.asyncio
    async def test_detects_pre_move_buying(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when address bought big before price increase."""
        engine = PreMoveEngine(settings=settings)

        # Price at t=0: 100
        await engine.on_asset_update(_snapshot("SOL", 0, 100.0))

        # 0xwhale buys heavily during t=0..59999 (pre-move window)
        for i in range(5):
            await engine.on_trade(
                _trade("SOL", "0xwhale", "0xmm", 100.0, 50.0, i * 10000, i)
            )
            # 5 * 100 * 50 = 25,000 > 10K threshold

        # Price at t=60000: still 100 (start of move window)
        await engine.on_asset_update(_snapshot("SOL", 60_000, 100.0))

        # Price at t=120000: 103 (3% up)
        await engine.on_asset_update(_snapshot("SOL", 120_000, 103.0))

        alerts = await engine.tick(120_000)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "pre_move"
        assert "0xwhale" in str(alerts[0].metadata.get("top_addresses", []))

    @pytest.mark.asyncio
    async def test_detects_pre_move_selling(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Alert fires when address sold big before price decrease."""
        engine = PreMoveEngine(settings=settings)

        await engine.on_asset_update(_snapshot("BTC", 0, 50000.0))

        # 0xseller sells during pre-move window
        for i in range(3):
            await engine.on_trade(
                _trade("BTC", "0xmm", "0xseller", 50000.0, 1.0, i * 10000, i)
            )
            # seller's flow: 3 * -50000 = -150,000 (net short)

        await engine.on_asset_update(_snapshot("BTC", 60_000, 50000.0))
        await engine.on_asset_update(_snapshot("BTC", 120_000, 48500.0))
        # 3% drop

        alerts = await engine.tick(120_000)
        assert len(alerts) == 1
        assert "0xseller" in str(alerts[0].metadata.get("top_addresses", []))

    @pytest.mark.asyncio
    async def test_no_alert_small_move(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when price move is below threshold."""
        engine = PreMoveEngine(settings=settings)

        await engine.on_asset_update(_snapshot("ETH", 0, 2000.0))

        for i in range(5):
            await engine.on_trade(
                _trade("ETH", "0xbig", "0xmm", 2000.0, 50.0, i * 10000, i)
            )

        await engine.on_asset_update(_snapshot("ETH", 60_000, 2000.0))
        # Only 0.5% move
        await engine.on_asset_update(_snapshot("ETH", 120_000, 2010.0))

        alerts = await engine.tick(120_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_no_alert_small_volume(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """No alert when pre-move volume is below min notional."""
        engine = PreMoveEngine(settings=settings)

        await engine.on_asset_update(_snapshot("SOL", 0, 100.0))

        # Tiny trade: 100 * 0.1 = $10, well below 10K threshold
        await engine.on_trade(_trade("SOL", "0xtiny", "0xmm", 100.0, 0.1, 5000, 1))

        await engine.on_asset_update(_snapshot("SOL", 60_000, 100.0))
        await engine.on_asset_update(_snapshot("SOL", 120_000, 105.0))

        alerts = await engine.tick(120_000)
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """Cooldown prevents repeated alerts for the same coin."""
        settings.pre_move_cooldown_ms = 300_000
        engine = PreMoveEngine(settings=settings)

        await engine.on_asset_update(_snapshot("SOL", 0, 100.0))
        for i in range(5):
            await engine.on_trade(
                _trade("SOL", "0xwhale", "0xmm", 100.0, 50.0, i * 10000, i)
            )
        await engine.on_asset_update(_snapshot("SOL", 60_000, 100.0))
        await engine.on_asset_update(_snapshot("SOL", 120_000, 103.0))

        alerts1 = await engine.tick(120_000)
        assert len(alerts1) == 1

        # Second tick should be suppressed by cooldown
        alerts2 = await engine.tick(121_000)
        assert len(alerts2) == 0

    @pytest.mark.asyncio
    async def test_on_trade_returns_empty(
        self,
        settings: HyperSussySettings,
    ) -> None:
        """on_trade always returns empty list."""
        engine = PreMoveEngine(settings=settings)
        result = await engine.on_trade(
            _trade("BTC", "0xa", "0xb", 50000.0, 1.0, 1000, 1)
        )
        assert result == []
