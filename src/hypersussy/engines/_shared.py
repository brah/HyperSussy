"""Shared helpers for detection engines."""

from __future__ import annotations


def is_on_cooldown(
    last_alert_ms: dict[str, int],
    key: str,
    timestamp_ms: int,
    cooldown_ms: int,
) -> bool:
    """Return whether a per-key cooldown is still active."""
    if key not in last_alert_ms:
        return False
    return timestamp_ms - last_alert_ms[key] < cooldown_ms


def record_alert_timestamp(
    last_alert_ms: dict[str, int],
    key: str,
    timestamp_ms: int,
) -> None:
    """Record the latest alert timestamp for a cooldown key."""
    last_alert_ms[key] = timestamp_ms
