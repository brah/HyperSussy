"""Tests for TuiSink."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hypersussy.alerts.sinks.tui_sink import TuiSink
from hypersussy.models import Alert
from hypersussy.tui.messages import DataBus


@pytest.fixture
def alert() -> Alert:
    """Minimal Alert for testing."""
    return Alert(
        alert_id="sink-test-id",
        alert_type="funding_anomaly",
        severity="critical",
        coin="ETH",
        title="Funding spike",
        description="Funding z-score exceeded 4.0",
        timestamp_ms=2_000_000,
        metadata={"zscore": 4.2, "funding_rate": 0.002},
    )


@pytest.mark.asyncio
async def test_tui_sink_calls_push_alert(alert: Alert) -> None:
    """TuiSink.send() must call data_bus.push_alert() with the alert."""
    bus = MagicMock(spec=DataBus)
    sink = TuiSink(bus)
    await sink.send(alert)
    bus.push_alert.assert_called_once_with(alert)


@pytest.mark.asyncio
async def test_tui_sink_does_not_call_push_snapshot(alert: Alert) -> None:
    """TuiSink.send() must not call push_snapshot."""
    bus = MagicMock(spec=DataBus)
    sink = TuiSink(bus)
    await sink.send(alert)
    bus.push_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_tui_sink_send_is_awaitable(alert: Alert) -> None:
    """TuiSink.send() must be an awaitable (satisfies AlertSink protocol)."""
    bus = MagicMock(spec=DataBus)
    sink = TuiSink(bus)
    # If this raises, send() is not properly async
    result = await sink.send(alert)
    assert result is None
