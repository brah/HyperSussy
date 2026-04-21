"""Thread-safe shared state between the background runner and API."""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass

from hypersussy.models import Alert, AssetSnapshot, CandleBar


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


@dataclass(frozen=True, slots=True)
class CandleEntry:
    """The latest candle for a (coin, interval) pair plus a change marker.

    Args:
        bar: The most recently received CandleBar from the HL WS.
        seq: Process-monotonic counter bumped on every push. WS clients
            track the last seq they sent so they can detect a tick
            without comparing the bar contents.
    """

    bar: CandleBar
    seq: int


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
        self._log_path: str | None = None
        # Live candle state — populated by CandleStreamRegistry from
        # the HL `candle` WS channel and consumed by /ws/live clients.
        # The desired-keys map is a refcount per (coin, interval); the
        # registry's reconcile loop reads the keys and subscribes/
        # unsubscribes against HL accordingly.
        self._desired_candle_keys: dict[tuple[str, str], int] = {}
        self._last_candles: dict[tuple[str, str], CandleEntry] = {}
        self._candle_seq_counter: int = 0

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
        """Return recent alerts newest-first.

        Materialises only ``limit`` items via :func:`itertools.islice`
        on a reversed iterator instead of building two N-sized lists.
        Iteration must run inside the lock — mutating the deque while
        a reverse-iterator is live raises ``RuntimeError``.
        """
        with self._lock:
            return list(itertools.islice(reversed(self._alerts), limit))

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
            return {name: issue.message for name, issue in self._engine_errors.items()}

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
            return {name: issue.message for name, issue in self._runtime_errors.items()}

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

    def set_log_path(self, path: str) -> None:
        """Record the path to the background runner's log file."""
        with self._lock:
            self._log_path = path

    def get_log_path(self) -> str | None:
        """Return the log file path, or None if not yet set."""
        with self._lock:
            return self._log_path

    # ── Live candles ────────────────────────────────────────────

    def acquire_candle_subscription(self, coin: str, interval: str) -> None:
        """Reserve a HL candle subscription for ``(coin, interval)``.

        Refcounted: multiple ``/ws/live`` clients viewing the same
        ``(coin, interval)`` pair share one upstream HL subscription.
        The reconcile loop in CandleStreamRegistry reads
        :meth:`get_desired_candle_keys` to know what HL subscriptions
        should currently exist.

        Args:
            coin: Asset ticker.
            interval: HL candle interval string (e.g. ``"1m"``).
        """
        key = (coin, interval)
        with self._lock:
            self._desired_candle_keys[key] = self._desired_candle_keys.get(key, 0) + 1

    def release_candle_subscription(self, coin: str, interval: str) -> None:
        """Drop one reference to ``(coin, interval)``.

        When the refcount reaches zero the key is removed from the
        desired set *and* any cached bar is evicted from
        ``_last_candles``; the reconcile loop will subsequently
        unsubscribe from HL on its next tick. Without the cache
        eviction, a long session that browses many symbols/intervals
        would retain every bar it ever saw.

        Args:
            coin: Asset ticker.
            interval: HL candle interval string.
        """
        key = (coin, interval)
        with self._lock:
            count = self._desired_candle_keys.get(key, 0)
            if count <= 1:
                self._desired_candle_keys.pop(key, None)
                self._last_candles.pop(key, None)
            else:
                self._desired_candle_keys[key] = count - 1

    def get_desired_candle_keys(self) -> set[tuple[str, str]]:
        """Return a snapshot of all currently-desired candle keys."""
        with self._lock:
            return set(self._desired_candle_keys.keys())

    def push_candle(self, bar: CandleBar) -> None:
        """Store the latest candle for one (coin, interval).

        Bumps the per-process sequence counter so consumers can detect
        an update without comparing bar contents. Silently drops bars
        for keys no client currently wants — closes the race between
        ``release_candle_subscription`` evicting the cache entry and a
        trailing HL message for the same key re-inserting it (which
        would leak the entry forever since nothing would ever release
        it again).

        Args:
            bar: The candle bar to store.
        """
        key = (bar.coin, bar.interval)
        with self._lock:
            if key not in self._desired_candle_keys:
                return
            self._candle_seq_counter += 1
            self._last_candles[key] = CandleEntry(bar=bar, seq=self._candle_seq_counter)

    def get_candle_entry(self, coin: str, interval: str) -> CandleEntry | None:
        """Return the latest candle entry for ``(coin, interval)``.

        Args:
            coin: Asset ticker.
            interval: HL candle interval string.

        Returns:
            The candle entry, or ``None`` if no candle has been
            received for this key yet.
        """
        with self._lock:
            return self._last_candles.get((coin, interval))
