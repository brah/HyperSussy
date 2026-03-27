"""Tests for AppSink."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from hypersussy.app.sink import AppSink
from hypersussy.app.state import SharedState
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


def test_send_calls_push_alert(alert: Alert) -> None:
    """send() must call state.push_alert() exactly once with the alert."""
    state = MagicMock(spec=SharedState)
    sink = AppSink(state)
    asyncio.run(sink.send(alert))
    state.push_alert.assert_called_once_with(alert)


def test_send_is_awaitable(alert: Alert) -> None:
    """send() must be awaitable and return None."""
    state = MagicMock(spec=SharedState)
    sink = AppSink(state)
    result = asyncio.run(sink.send(alert))
    assert result is None


def test_send_does_not_touch_snapshots(alert: Alert) -> None:
    """send() must not call push_snapshot."""
    state = MagicMock(spec=SharedState)
    sink = AppSink(state)
    asyncio.run(sink.send(alert))
    state.push_snapshot.assert_not_called()
