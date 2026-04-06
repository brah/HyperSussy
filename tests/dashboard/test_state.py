"""Tests for SharedState thread safety and DataBus conformance."""

from __future__ import annotations

import threading

import pytest

from hypersussy.app.state import SharedState
from hypersussy.models import Alert, AssetSnapshot

# -- Fixtures --

@pytest.fixture
def state() -> SharedState:
    """SharedState with a small alert cap for testing."""
    return SharedState(max_alerts=10)


def _make_snapshot(coin: str, timestamp_ms: int = 1_000_000) -> AssetSnapshot:
    """Build a minimal AssetSnapshot for a given coin."""
    return AssetSnapshot(
        coin=coin,
        timestamp_ms=timestamp_ms,
        open_interest=1000.0,
        open_interest_usd=50_000.0,
        mark_price=50.0,
        oracle_price=50.1,
        funding_rate=0.0001,
        premium=0.002,
        day_volume_usd=1_000_000.0,
    )


def _make_alert(coin: str = "BTC", timestamp_ms: int = 1_000_000) -> Alert:
    """Build a minimal Alert."""
    return Alert(
        alert_id=f"test-{coin}-{timestamp_ms}",
        alert_type="funding_anomaly",
        severity="low",
        coin=coin,
        title="Test alert",
        description="Test description",
        timestamp_ms=timestamp_ms,
    )


# -- Snapshot tests --

def test_push_snapshot_last_write_wins(state: SharedState) -> None:
    """Second push for the same coin overwrites the first."""
    snap1 = _make_snapshot("BTC", timestamp_ms=1_000)
    snap2 = _make_snapshot("BTC", timestamp_ms=2_000)
    state.push_snapshot(snap1)
    state.push_snapshot(snap2)
    snapshots = state.get_snapshots()
    assert len(snapshots) == 1
    assert snapshots["BTC"].timestamp_ms == 2_000


def test_push_snapshot_multiple_coins(state: SharedState) -> None:
    """Each coin gets its own entry in the snapshots dict."""
    state.push_snapshot(_make_snapshot("BTC"))
    state.push_snapshot(_make_snapshot("ETH"))
    snapshots = state.get_snapshots()
    assert set(snapshots.keys()) == {"BTC", "ETH"}


def test_push_snapshot_concurrent(state: SharedState) -> None:
    """Concurrent pushes from 10 threads must not corrupt state."""
    coins = [f"COIN{i}" for i in range(10)]
    errors: list[Exception] = []

    def push(coin: str) -> None:
        try:
            for _ in range(50):
                state.push_snapshot(_make_snapshot(coin))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=push, args=(c,)) for c in coins]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    snapshots = state.get_snapshots()
    assert set(snapshots.keys()) == set(coins)


def test_get_snapshots_returns_copy(state: SharedState) -> None:
    """Mutating the returned dict must not affect internal state."""
    state.push_snapshot(_make_snapshot("BTC"))
    copy = state.get_snapshots()
    copy["BTC"] = None  # type: ignore[assignment]
    assert state.get_snapshots()["BTC"] is not None


# -- Alert tests --

def test_push_alert_appends(state: SharedState) -> None:
    """Pushing an alert makes it retrievable via get_recent_alerts."""
    alert = _make_alert()
    state.push_alert(alert)
    assert alert in state.get_recent_alerts()


def test_alerts_bounded(state: SharedState) -> None:
    """Deque drops oldest entries once max_alerts is exceeded."""
    for i in range(15):
        state.push_alert(_make_alert(timestamp_ms=i))
    assert len(state.get_recent_alerts(limit=100)) == 10


def test_get_recent_alerts_newest_first(state: SharedState) -> None:
    """get_recent_alerts returns alerts newest-first."""
    for i in range(5):
        state.push_alert(_make_alert(timestamp_ms=i * 1000))
    alerts = state.get_recent_alerts()
    timestamps = [a.timestamp_ms for a in alerts]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_recent_alerts_limit(state: SharedState) -> None:
    """get_recent_alerts respects the limit argument."""
    for i in range(8):
        state.push_alert(_make_alert(timestamp_ms=i))
    assert len(state.get_recent_alerts(limit=3)) == 3


# -- Running flag --

def test_running_flag_default_false(state: SharedState) -> None:
    """is_running is False on construction."""
    assert state.is_running is False


def test_running_flag_set_true(state: SharedState) -> None:
    """set_running(True) reflects in is_running."""
    state.set_running(True)
    assert state.is_running is True


def test_running_flag_set_false(state: SharedState) -> None:
    """set_running(False) after True reflects in is_running."""
    state.set_running(True)
    state.set_running(False)
    assert state.is_running is False


# -- Engine errors --

def test_mark_engine_error_latest_wins(state: SharedState) -> None:
    """Two errors for same engine retain only the most recent."""
    state.mark_engine_error("oi_concentration", "first error")
    state.mark_engine_error("oi_concentration", "second error")
    errors = state.get_engine_errors()
    assert errors["oi_concentration"] == "second error"


def test_get_engine_errors_returns_copy(state: SharedState) -> None:
    """Mutating the returned dict does not affect internal state."""
    state.mark_engine_error("whale_tracker", "err")
    copy = state.get_engine_errors()
    del copy["whale_tracker"]
    assert "whale_tracker" in state.get_engine_errors()


def test_runtime_errors_latest_wins(state: SharedState) -> None:
    """Runtime errors keep only the newest message per source."""
    state.mark_runtime_error("runner", "first")
    state.mark_runtime_error("runner", "second")
    assert state.get_runtime_errors()["runner"] == "second"


def test_clear_runtime_error_removes_entry(state: SharedState) -> None:
    """Clearing a runtime error removes it from the public copy."""
    state.mark_runtime_error("runner", "boom")
    state.clear_runtime_error("runner")
    assert "runner" not in state.get_runtime_errors()


def test_runtime_health_tracks_last_snapshot_and_alert(state: SharedState) -> None:
    """Runtime health exposes the latest snapshot and alert timestamps."""
    state.push_snapshot(_make_snapshot("BTC", timestamp_ms=12_345))
    state.push_alert(_make_alert(timestamp_ms=67_890))
    health = state.get_runtime_health()
    assert health.snapshot_count == 1
    assert health.last_snapshot_ms == 12_345
    assert health.last_alert_ms == 67_890


def test_runtime_health_exposes_issue_objects(state: SharedState) -> None:
    """Runtime health returns immutable issue snapshots for UI display."""
    state.mark_engine_error("oi_concentration", "engine failure")
    state.mark_runtime_error("runner", "runtime failure")
    health = state.get_runtime_health()
    assert health.engine_errors[0].source == "oi_concentration"
    assert health.runtime_errors[0].source == "runner"
