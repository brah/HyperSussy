"""Tests for get_latest_positions storage method."""

from __future__ import annotations

import pytest

from hypersussy.models import Position
from hypersussy.storage.sqlite import SqliteStorage


class TestGetLatestPositions:
    """Tests for SqliteStorage.get_latest_positions."""

    @pytest.mark.asyncio
    async def test_returns_latest_per_coin(self, storage: SqliteStorage) -> None:
        """Returns the most recent position for each coin."""
        positions = [
            Position(
                coin="BTC",
                address="0xabc",
                size=5.0,
                entry_price=50000.0,
                mark_price=50000.0,
                liquidation_price=40000.0,
                unrealized_pnl=0.0,
                margin_used=50000.0,
                leverage_value=5,
                leverage_type="cross",
                notional_usd=250_000.0,
                timestamp_ms=1000,
            ),
            Position(
                coin="BTC",
                address="0xabc",
                size=10.0,
                entry_price=51000.0,
                mark_price=51000.0,
                liquidation_price=41000.0,
                unrealized_pnl=1000.0,
                margin_used=100000.0,
                leverage_value=5,
                leverage_type="cross",
                notional_usd=510_000.0,
                timestamp_ms=2000,
            ),
            Position(
                coin="ETH",
                address="0xabc",
                size=100.0,
                entry_price=2000.0,
                mark_price=2000.0,
                liquidation_price=1500.0,
                unrealized_pnl=0.0,
                margin_used=40000.0,
                leverage_value=5,
                leverage_type="cross",
                notional_usd=200_000.0,
                timestamp_ms=1500,
            ),
        ]
        await storage.insert_positions(positions)

        latest = await storage.get_latest_positions("0xabc")
        assert len(latest) == 2

        by_coin = {p.coin: p for p in latest}
        assert by_coin["BTC"].size == 10.0
        assert by_coin["BTC"].timestamp_ms == 2000
        assert by_coin["ETH"].size == 100.0

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_address(
        self, storage: SqliteStorage
    ) -> None:
        """Returns empty list for address with no positions."""
        latest = await storage.get_latest_positions("0xunknown")
        assert latest == []
