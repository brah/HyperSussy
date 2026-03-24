"""Tests for domain models."""

from __future__ import annotations

import pytest

from hypersussy.models import Alert, AssetSnapshot, L2Book, Position, Trade


class TestAssetSnapshot:
    """Tests for AssetSnapshot dataclass."""

    def test_creation(self) -> None:
        """AssetSnapshot can be created with required fields."""
        snap = AssetSnapshot(
            coin="BTC",
            timestamp_ms=1000,
            open_interest=100.0,
            open_interest_usd=5_000_000.0,
            mark_price=50000.0,
            oracle_price=50001.0,
            funding_rate=0.0001,
            premium=0.00005,
            day_volume_usd=1_000_000.0,
        )
        assert snap.coin == "BTC"
        assert snap.mid_price is None

    def test_frozen(self) -> None:
        """AssetSnapshot is immutable."""
        snap = AssetSnapshot(
            coin="ETH",
            timestamp_ms=1000,
            open_interest=50.0,
            open_interest_usd=100_000.0,
            mark_price=2000.0,
            oracle_price=2001.0,
            funding_rate=0.0,
            premium=0.0,
            day_volume_usd=500_000.0,
        )
        with pytest.raises(AttributeError):
            snap.coin = "SOL"  # type: ignore[misc]


class TestTrade:
    """Tests for Trade dataclass."""

    def test_defaults(self) -> None:
        """Trade has correct default exchange."""
        trade = Trade(
            coin="BTC",
            price=50000.0,
            size=1.0,
            side="B",
            timestamp_ms=1000,
            buyer="0xabc",
            seller="0xdef",
            tx_hash="0x123",
            tid=1,
        )
        assert trade.exchange == "hyperliquid"


class TestPosition:
    """Tests for Position dataclass."""

    def test_signed_size(self) -> None:
        """Position size is signed (negative = short)."""
        pos = Position(
            coin="ETH",
            address="0xabc",
            size=-10.0,
            entry_price=2000.0,
            mark_price=1950.0,
            liquidation_price=2200.0,
            unrealized_pnl=500.0,
            margin_used=1000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=19500.0,
            timestamp_ms=1000,
        )
        assert pos.size < 0


class TestL2Book:
    """Tests for L2Book dataclass."""

    def test_tuple_levels(self) -> None:
        """L2Book uses tuples for immutable levels."""
        book = L2Book(
            coin="BTC",
            timestamp_ms=1000,
            bids=((50000.0, 1.0), (49999.0, 2.0)),
            asks=((50001.0, 1.5), (50002.0, 3.0)),
        )
        assert len(book.bids) == 2
        assert len(book.asks) == 2


class TestAlert:
    """Tests for Alert dataclass."""

    def test_metadata_default(self) -> None:
        """Alert metadata defaults to empty dict."""
        alert = Alert(
            alert_id="test-id",
            alert_type="test",
            severity="low",
            coin="BTC",
            title="Test",
            description="Test description",
            timestamp_ms=1000,
        )
        assert alert.metadata == {}
        assert alert.exchange == "hyperliquid"
