"""Tests for WebSocket alert de-dup helpers."""

from __future__ import annotations

from collections import deque

from hypersussy.api.ws import _remember_sent_alerts, _select_unsent_alerts
from hypersussy.models import Alert


def _alert(alert_id: str, timestamp_ms: int) -> Alert:
    return Alert(
        alert_id=alert_id,
        alert_type="whale_position",
        severity="high",
        coin="BTC",
        title="test",
        description="test",
        timestamp_ms=timestamp_ms,
    )


def test_select_unsent_alerts_keeps_same_timestamp_ids_distinct() -> None:
    """Alerts sharing a timestamp must still be sent if their IDs differ."""
    first = _alert("a1", 1_000)
    second = _alert("a2", 1_000)

    unseen = _select_unsent_alerts([first, second], {"a1"})

    assert [alert.alert_id for alert in unseen] == ["a2"]


def test_remember_sent_alerts_bounds_id_cache() -> None:
    """The sent-alert cache should stay bounded while tracking membership."""
    seen_ids: set[str] = set()
    seen_order: deque[str] = deque()

    _remember_sent_alerts(
        [_alert(f"a{i}", i) for i in range(600)],
        seen_ids,
        seen_order,
    )

    assert len(seen_order) == 500
    assert len(seen_ids) == 500
    assert "a0" not in seen_ids
    assert "a599" in seen_ids
