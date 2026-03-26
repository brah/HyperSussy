"""Thread-safe shared state between the background runner and API."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from hypersussy.models import Alert, AssetSnapshot


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    """Condensed market snapshot stored in shared state."""

    coin: str
    mark_price: float
    open_interest_usd: float
    funding_rate: float
    premium: float
    day_volume_usd: float
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RuntimeIssue:
    """A captured engine or runtime issue for UI display."""

    source: str
    message: str
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    """Immutable summary of current runner health."""

    is_running: bool
    snapshot_count: int
    last_snapshot_ms: int | None
    last_alert_ms: int | None
    engine_errors: tuple[RuntimeIssue, ...]
    runtime_errors: tuple[RuntimeIssue, ...]


class SharedState:
    """Thread-safe store for live snapshots, alerts, and runtime health."""

    def __init__(self, max_alerts: int = 500) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, LiveSnapshot] = {}
        self._alerts: deque[Alert] = deque(maxlen=max_alerts)
        self._running = False
        self._engine_errors: dict[str, RuntimeIssue] = {}
        self._runtime_errors: dict[str, RuntimeIssue] = {}
        self._last_snapshot_ms: int | None = None
        self._last_alert_ms: int | None = None

    def push_snapshot(self, snapshot: AssetSnapshot) -> None:
        """Store the latest snapshot for one coin."""
        live = LiveSnapshot(
            coin=snapshot.coin,
            mark_price=snapshot.mark_price,
            open_interest_usd=snapshot.open_interest_usd,
            funding_rate=snapshot.funding_rate,
            premium=snapshot.premium,
            day_volume_usd=snapshot.day_volume_usd,
            timestamp_ms=snapshot.timestamp_ms,
        )
        with self._lock:
            self._snapshots[snapshot.coin] = live
            self._last_snapshot_ms = snapshot.timestamp_ms

    def push_alert(self, alert: Alert) -> None:
        """Append a new alert to the in-memory live feed."""
        with self._lock:
            self._alerts.append(alert)
            self._last_alert_ms = alert.timestamp_ms

    async def add_alert(self, alert: Alert) -> None:
        """Async compatibility wrapper for alert sinks."""
        self.push_alert(alert)

    def get_snapshots(self) -> dict[str, LiveSnapshot]:
        """Return a shallow copy of the live snapshots."""
        with self._lock:
            return dict(self._snapshots)

    def get_recent_alerts(self, limit: int = 100) -> list[Alert]:
        """Return recent alerts newest-first."""
        with self._lock:
            alerts = list(self._alerts)
        return list(reversed(alerts))[:limit]

    def mark_engine_error(self, engine_name: str, error: str) -> None:
        """Record the latest error for an engine."""
        issue = RuntimeIssue(
            source=engine_name,
            message=error,
            timestamp_ms=int(time.time() * 1000),
        )
        with self._lock:
            self._engine_errors[engine_name] = issue

    def clear_engine_error(self, engine_name: str) -> None:
        """Clear a previously recorded engine error."""
        with self._lock:
            self._engine_errors.pop(engine_name, None)

    def get_engine_errors(self) -> dict[str, str]:
        """Return the latest engine error messages."""
        with self._lock:
            return {
                name: issue.message for name, issue in self._engine_errors.items()
            }

    def mark_runtime_error(self, source: str, error: str) -> None:
        """Record a runtime error for UI visibility."""
        issue = RuntimeIssue(
            source=source,
            message=error,
            timestamp_ms=int(time.time() * 1000),
        )
        with self._lock:
            self._runtime_errors[source] = issue

    def clear_runtime_error(self, source: str) -> None:
        """Clear a previously recorded runtime error."""
        with self._lock:
            self._runtime_errors.pop(source, None)

    def get_runtime_errors(self) -> dict[str, str]:
        """Return the latest runtime error messages."""
        with self._lock:
            return {
                name: issue.message for name, issue in self._runtime_errors.items()
            }

    def get_runtime_health(self) -> RuntimeHealth:
        """Return an immutable snapshot of current runtime health."""
        with self._lock:
            return RuntimeHealth(
                is_running=self._running,
                snapshot_count=len(self._snapshots),
                last_snapshot_ms=self._last_snapshot_ms,
                last_alert_ms=self._last_alert_ms,
                engine_errors=tuple(self._engine_errors.values()),
                runtime_errors=tuple(self._runtime_errors.values()),
            )

    def set_running(self, value: bool) -> None:
        """Update the runner active flag."""
        with self._lock:
            self._running = value

    @property
    def is_running(self) -> bool:
        """True while the background runner is active."""
        with self._lock:
            return self._running
