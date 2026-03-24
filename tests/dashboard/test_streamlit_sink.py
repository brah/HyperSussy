"""Tests for StreamlitSink."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hypersussy.dashboard.sink import StreamlitSink
from hypersussy.dashboard.state import SharedState
from hypersussy.models import Alert


@pytest.fixture
def alert() -> Alert:
    """Minimal Alert fixture."""
    return Alert(
        alert_id="streamlit-sink-test",
        alert_type="pre_move",
        severity="high",
        coin="SOL",
        title="Pre-move detected",
        description="Informed trading detected before a 3% price move.",
        timestamp_ms=3_000_000,
        metadata={"score": 42.1},
    )


@pytest.mark.asyncio
async def test_send_calls_push_alert(alert: Alert) -> None:
    """send() must call state.push_alert() exactly once with the alert."""
    state = MagicMock(spec=SharedState)
    sink = StreamlitSink(state)
    await sink.send(alert)
    state.push_alert.assert_called_once_with(alert)


@pytest.mark.asyncio
async def test_send_is_awaitable(alert: Alert) -> None:
    """send() must be awaitable and return None."""
    state = MagicMock(spec=SharedState)
    sink = StreamlitSink(state)
    result = await sink.send(alert)
    assert result is None


@pytest.mark.asyncio
async def test_send_does_not_touch_snapshots(alert: Alert) -> None:
    """send() must not call push_snapshot."""
    state = MagicMock(spec=SharedState)
    sink = StreamlitSink(state)
    await sink.send(alert)
    state.push_snapshot.assert_not_called()
