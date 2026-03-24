"""Tests for TUI messages and DataBus protocol."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from textual.message import Message

from hypersussy.models import Alert, AssetSnapshot
from hypersussy.tui.messages import AlertReceived, DataBus, SnapshotUpdated


@pytest.fixture
def snapshot() -> AssetSnapshot:
    """Minimal AssetSnapshot for testing."""
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


@pytest.fixture
def alert() -> Alert:
    """Minimal Alert for testing."""
    return Alert(
        alert_id="test-id",
        alert_type="oi_concentration",
        severity="high",
        coin="BTC",
        title="OI spike",
        description="Open interest jumped 15%",
        timestamp_ms=1_000_000,
        metadata={"delta_pct": 15.0},
    )


def test_snapshot_updated_is_message(snapshot: AssetSnapshot) -> None:
    """SnapshotUpdated must be a Textual Message subclass."""
    msg = SnapshotUpdated(snapshot)
    assert isinstance(msg, Message)


def test_snapshot_updated_carries_snapshot(snapshot: AssetSnapshot) -> None:
    """SnapshotUpdated must expose the snapshot attribute."""
    msg = SnapshotUpdated(snapshot)
    assert msg.snapshot is snapshot


def test_alert_received_is_message(alert: Alert) -> None:
    """AlertReceived must be a Textual Message subclass."""
    msg = AlertReceived(alert)
    assert isinstance(msg, Message)


def test_alert_received_carries_alert(alert: Alert) -> None:
    """AlertReceived must expose the alert attribute."""
    msg = AlertReceived(alert)
    assert msg.alert is alert


def test_data_bus_protocol_satisfied_by_mock() -> None:
    """Any object with push_snapshot and push_alert satisfies DataBus."""
    bus = MagicMock(spec=DataBus)
    # Runtime structural check — both methods must be present
    assert hasattr(bus, "push_snapshot")
    assert hasattr(bus, "push_alert")
