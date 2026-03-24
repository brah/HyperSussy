"""Tests for MarketTable widget."""

from __future__ import annotations

import pytest

from hypersussy.models import AssetSnapshot
from hypersussy.tui.app import HyperSussyApp
from hypersussy.tui.widgets.market_table import (
    MarketTable,
    _fmt_price,
    _fmt_rate,
    _fmt_usd,
)

# ------------------------------------------------------------------
# Pure formatting helpers — no Textual needed
# ------------------------------------------------------------------


def test_fmt_price_large() -> None:
    """Prices >= 1000 should include comma separator."""
    assert "," in _fmt_price(50_000.0)


def test_fmt_price_small() -> None:
    """Prices < 1 should have 6 decimal places."""
    result = _fmt_price(0.000123)
    assert "0.000123" in result


def test_fmt_usd_millions() -> None:
    """Values in millions should show M suffix."""
    assert "M" in _fmt_usd(50_000_000.0)


def test_fmt_usd_billions() -> None:
    """Values in billions should show B suffix."""
    assert "B" in _fmt_usd(2_000_000_000.0)


def test_fmt_rate_positive() -> None:
    """Positive rates should have a leading + sign."""
    assert _fmt_rate(0.0001).startswith("+")


def test_fmt_rate_negative() -> None:
    """Negative rates should have a leading - sign."""
    assert _fmt_rate(-0.0001).startswith("-")


# ------------------------------------------------------------------
# Widget integration tests using Textual Pilot
# ------------------------------------------------------------------


@pytest.fixture
def snapshot() -> AssetSnapshot:
    """BTC snapshot fixture."""
    return AssetSnapshot(
        coin="BTC",
        timestamp_ms=1_000_000,
        open_interest=1000.0,
        open_interest_usd=50_000_000.0,
        mark_price=50_000.0,
        oracle_price=50_010.0,
        funding_rate=0.0001,
        premium=0.0002,
        day_volume_usd=1_000_000_000.0,
    )


@pytest.mark.asyncio
async def test_market_table_adds_row(snapshot: AssetSnapshot) -> None:
    """push_snapshot should add a row for a new coin."""
    app = HyperSussyApp()
    async with app.run_test() as pilot:
        app.push_snapshot(snapshot)
        await pilot.pause()
        await pilot.pause()

        table = app.query_one(MarketTable)
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_market_table_updates_existing_row(snapshot: AssetSnapshot) -> None:
    """Calling push_snapshot twice for the same coin should not add a second row."""
    app = HyperSussyApp()
    async with app.run_test() as pilot:
        app.push_snapshot(snapshot)
        await pilot.pause()
        await pilot.pause()

        updated = AssetSnapshot(
            coin="BTC",
            timestamp_ms=2_000_000,
            open_interest=1100.0,
            open_interest_usd=55_000_000.0,
            mark_price=51_000.0,
            oracle_price=51_010.0,
            funding_rate=0.0002,
            premium=0.0003,
            day_volume_usd=1_100_000_000.0,
        )
        app.push_snapshot(updated)
        await pilot.pause()
        await pilot.pause()

        table = app.query_one(MarketTable)
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_market_table_multiple_coins() -> None:
    """Each unique coin should produce a separate row."""
    app = HyperSussyApp()
    async with app.run_test() as pilot:
        for coin in ("BTC", "ETH", "SOL"):
            snap = AssetSnapshot(
                coin=coin,
                timestamp_ms=1_000_000,
                open_interest=100.0,
                open_interest_usd=1_000_000.0,
                mark_price=100.0,
                oracle_price=100.0,
                funding_rate=0.0001,
                premium=0.0,
                day_volume_usd=10_000_000.0,
            )
            app.push_snapshot(snap)
        await pilot.pause()
        await pilot.pause()

        table = app.query_one(MarketTable)
        assert table.row_count == 3
