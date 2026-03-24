"""Tests for AlertFeed widget."""

from __future__ import annotations

import pytest

from hypersussy.models import Alert
from hypersussy.tui.app import HyperSussyApp
from hypersussy.tui.messages import AlertReceived
from hypersussy.tui.widgets.alert_feed import (
    AlertFeed,
    _format_alert_row,
    _severity_badge,
)

# ------------------------------------------------------------------
# Pure formatting helpers
# ------------------------------------------------------------------


def test_severity_badge_contains_severity() -> None:
    """Severity badge markup must include the severity text in uppercase."""
    badge = _severity_badge("critical")
    assert "CRITICAL" in badge


def test_severity_badge_unknown_severity() -> None:
    """Unknown severity should still produce a non-empty badge."""
    badge = _severity_badge("unknown")
    assert "UNKNOWN" in badge


def test_format_alert_row_contains_coin(alert_fixture: Alert) -> None:
    """Formatted row must contain the coin name."""
    row = _format_alert_row(alert_fixture)
    assert alert_fixture.coin in row


def test_format_alert_row_contains_title(alert_fixture: Alert) -> None:
    """Formatted row must contain the alert title."""
    row = _format_alert_row(alert_fixture)
    assert alert_fixture.title in row


# ------------------------------------------------------------------
# Widget integration tests
# ------------------------------------------------------------------


@pytest.fixture
def alert_fixture() -> Alert:
    """Sample Alert for testing."""
    return Alert(
        alert_id="feed-test-id",
        alert_type="whale_position",
        severity="high",
        coin="SOL",
        title="Large whale position",
        description="Whale holds 8% of OI",
        timestamp_ms=3_000_000,
        metadata={"oi_pct": 8.0, "notional_usd": 10_000_000.0},
    )


@pytest.mark.asyncio
async def test_alert_feed_prepends_item(alert_fixture: Alert) -> None:
    """push_alert should add an item to the feed."""
    app = HyperSussyApp()
    async with app.run_test() as pilot:
        app.push_alert(alert_fixture)
        await pilot.pause()
        await pilot.pause()

        feed = app.query_one(AlertFeed)
        assert len(feed._nodes) == 1  # noqa: SLF001


@pytest.mark.asyncio
async def test_alert_feed_newest_first() -> None:
    """Alerts must be prepended so the newest appears first."""
    app = HyperSussyApp()
    async with app.run_test() as pilot:
        for i in range(3):
            alert = Alert(
                alert_id=f"id-{i}",
                alert_type="oi_concentration",
                severity="low",
                coin="BTC",
                title=f"Alert {i}",
                description="desc",
                timestamp_ms=i * 1000,
            )
            app.push_alert(alert)
        await pilot.pause()
        await pilot.pause()

        feed = app.query_one(AlertFeed)
        # First item should carry the last-posted alert (highest index)
        first_item = feed._nodes[0]  # noqa: SLF001
        assert first_item.alert.alert_id == "id-2"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_alert_feed_status_bar_updated(alert_fixture: Alert) -> None:
    """Posting an alert should update the StatusBar last_alert_ts."""
    from hypersussy.tui.widgets.status_bar import StatusBar

    app = HyperSussyApp()
    async with app.run_test() as pilot:
        app.post_message(AlertReceived(alert_fixture))
        await pilot.pause()

        status = app.query_one(StatusBar)
        assert status.last_alert_ts == alert_fixture.timestamp_ms
