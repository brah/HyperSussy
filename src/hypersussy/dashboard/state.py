"""Thread-safe shared state between the orchestrator thread and Streamlit.

SharedState implements the DataBus protocol so it can be passed directly
to the Orchestrator as its data_bus argument, receiving snapshots and alerts
from the same push interface used by the TUI.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from hypersussy.models import Alert, AssetSnapshot


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    """Condensed, mutable market snapshot held in SharedState.

    Attributes:
        coin: Asset ticker symbol.
        mark_price: Current mark price in USD.
        open_interest_usd: Open interest denominated in USD.
        funding_rate: Current hourly funding rate.
        premium: Mark/oracle price premium.
        day_volume_usd: 24-hour volume in USD.
        timestamp_ms: Unix timestamp of the snapshot in milliseconds.
    """

    coin: str
    mark_price: float
    open_interest_usd: float
    funding_rate: float
    premium: float
    day_volume_usd: float
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RuntimeIssue:
    """A captured engine or runtime issue for dashboard display."""

    source: str
    message: str
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    """Immutable summary of current dashboard runtime health."""

    is_running: bool
    snapshot_count: int
    last_snapshot_ms: int | None
    last_alert_ms: int | None
    engine_errors: tuple[RuntimeIssue, ...]
    runtime_errors: tuple[RuntimeIssue, ...]


class SharedState:
    """Thread-safe store for live market data and alerts.

    Implements the DataBus protocol (push_snapshot / push_alert) so it can
    be passed as data_bus to the Orchestrator. All mutations are protected
    by an RLock; reads return shallow copies to avoid external mutation.

    Args:
        max_alerts: Maximum number of alerts retained in the deque.
    """

    def __init__(self, max_alerts: int = 500) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, LiveSnapshot] = {}
        self._alerts: deque[Alert] = deque(maxlen=max_alerts)
        self._running = False
        self._engine_errors: dict[str, RuntimeIssue] = {}
        self._runtime_errors: dict[str, RuntimeIssue] = {}
        self._last_snapshot_ms: int | None = None
        self._last_alert_ms: int | None = None

    # -- DataBus protocol --

    def push_snapshot(self, snapshot: AssetSnapshot) -> None:
        """Overwrite the latest snapshot for a coin.

        Args:
            snapshot: The incoming asset snapshot.
        """
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
        """Append an alert to the live deque.

        Args:
            alert: The dispatched alert.
        """
        with self._lock:
            self._alerts.append(alert)
            self._last_alert_ms = alert.timestamp_ms

    # -- Read interface for Streamlit --

    def get_snapshots(self) -> dict[str, LiveSnapshot]:
        """Return a shallow copy of the current snapshots dict.

        Returns:
            Mapping of coin symbol to its latest LiveSnapshot.
        """
        with self._lock:
            return dict(self._snapshots)

    def get_recent_alerts(self, limit: int = 100) -> list[Alert]:
        """Return the most recent alerts as a list, newest-first.

        Args:
            limit: Maximum number of alerts to return.

        Returns:
            List of Alert objects ordered from newest to oldest.
        """
        with self._lock:
            alerts = list(self._alerts)
        return list(reversed(alerts))[:limit]

    def mark_engine_error(self, engine_name: str, error: str) -> None:
        """Record the latest error for an engine.

        Args:
            engine_name: Name of the detection engine.
            error: Error message string.
        """
        issue = RuntimeIssue(
            source=engine_name,
            message=error,
            timestamp_ms=int(time.time() * 1000),
        )
        with self._lock:
            self._engine_errors[engine_name] = issue

    def clear_engine_error(self, engine_name: str) -> None:
        """Clear the latest recorded error for an engine."""
        with self._lock:
            self._engine_errors.pop(engine_name, None)

    def get_engine_errors(self) -> dict[str, str]:
        """Return a copy of the latest error per engine.

        Returns:
            Mapping of engine name to its most recent error message.
        """
        with self._lock:
            return {
                name: issue.message for name, issue in self._engine_errors.items()
            }

    def mark_runtime_error(self, source: str, error: str) -> None:
        """Record a non-engine runtime error for dashboard visibility."""
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
        """Return a copy of the latest non-engine runtime errors."""
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
        """Update the running flag (called by BackgroundRunner).

        Args:
            value: True when the orchestrator loop is active.
        """
        with self._lock:
            self._running = value

    @property
    def is_running(self) -> bool:
        """True while the background orchestrator thread is active."""
        with self._lock:
            return self._running
