"""Alert manager with deduplication, throttling, and dispatch."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Sequence

from hypersussy.alerts.base import AlertSink
from hypersussy.config import HyperSussySettings
from hypersussy.models import Alert
from hypersussy.storage.base import StorageProtocol

# Cap on entries retained in the in-memory fingerprint cache. Each
# entry holds ~200 bytes, so 4096 ≈ 800 KB worst case. Pruned on
# every process_alert so the steady-state size is bounded by the
# alert burst volume in the last ``alert_cooldown_s`` seconds.
_FINGERPRINT_CACHE_MAX = 4096


class AlertManager:
    """Processes alerts through dedup, throttle, then dispatch.

    Dedup runs entirely from an in-memory fingerprint → last-dispatched
    map. On startup the map is empty, so the first cooldown window per
    fingerprint falls through to storage as a safety net. Subsequent
    checks never touch storage, turning a burst of N alerts on one
    (type, coin, address) key from N SQLite scans into N dict lookups.

    Args:
        storage: Storage backend for persistence and first-boot fallback.
        sinks: Alert delivery backends.
        settings: Application settings with alert thresholds.
    """

    def __init__(
        self,
        storage: StorageProtocol,
        sinks: Sequence[AlertSink],
        settings: HyperSussySettings,
    ) -> None:
        self._storage = storage
        self._sinks = sinks
        self._settings = settings
        # Global throttle: timestamps of recent dispatches. Sized to
        # hold at least ``alert_max_per_minute`` entries plus headroom
        # so the deque's maxlen never silently drops before prune runs.
        buffer_size = max(1024, settings.alert_max_per_minute * 8)
        self._dispatch_times: deque[float] = deque(maxlen=buffer_size)
        # In-memory dedup cache: fingerprint → last_dispatched_ms.
        # Populated on first sighting per fingerprint (falls through
        # to storage then) and on every successful dispatch.
        self._fingerprint_last_ms: dict[tuple[str, ...], int] = {}
        # Fingerprints already verified against storage on this process —
        # prevents repeated storage round-trips for keys that aren't in
        # the live cache yet but have been confirmed absent from storage.
        self._storage_checked: set[tuple[str, ...]] = set()

    async def process_alert(self, alert: Alert) -> bool:
        """Deduplicate, throttle, persist, then dispatch an alert.

        Args:
            alert: The alert to process.

        Returns:
            True if the alert was dispatched, False if suppressed.
        """
        fingerprint = self._dedupe_fingerprint(alert)
        if await self._is_duplicate(alert, fingerprint):
            return False

        if self._is_throttled():
            return False

        await self._storage.insert_alert(alert)
        now_mono = time.monotonic()
        self._dispatch_times.append(now_mono)
        self._fingerprint_last_ms[fingerprint] = alert.timestamp_ms
        self._prune_fingerprint_cache(alert.timestamp_ms)

        await asyncio.gather(*(sink.send(alert) for sink in self._sinks))

        return True

    async def _is_duplicate(
        self,
        alert: Alert,
        fingerprint: tuple[str, ...],
    ) -> bool:
        """Check whether a similar alert was recently fired.

        First consults the in-memory fingerprint cache. On a miss,
        falls back to storage *exactly once* per fingerprint per
        process so a cooldown that outlived a process restart still
        applies. After that, the in-memory cache is authoritative.

        Args:
            alert: The alert to check.
            fingerprint: Pre-computed dedup fingerprint for ``alert``.

        Returns:
            True if a duplicate exists within the cooldown window.
        """
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        cutoff_ms = alert.timestamp_ms - cooldown_ms

        last_ms = self._fingerprint_last_ms.get(fingerprint)
        if last_ms is not None:
            return last_ms >= cutoff_ms

        if fingerprint in self._storage_checked:
            return False

        # Never-before-seen fingerprint on this process — hit storage
        # once to honour a cooldown that straddles a restart.
        recent = await self._storage.get_recent_alerts(
            alert.alert_type, alert.coin, cutoff_ms, limit=20
        )
        self._storage_checked.add(fingerprint)
        for existing in recent:
            if self._dedupe_fingerprint(existing) == fingerprint:
                # Seed the cache with the existing timestamp so the
                # next check short-circuits without another storage hit.
                self._fingerprint_last_ms[fingerprint] = existing.timestamp_ms
                return existing.timestamp_ms >= cutoff_ms
        return False

    def _prune_fingerprint_cache(self, now_ms: int) -> None:
        """Drop fingerprints older than the cooldown window.

        Bounded at ``_FINGERPRINT_CACHE_MAX`` as a safety valve in
        case the cooldown is misconfigured to effectively-forever and
        every alert has a unique fingerprint.
        """
        cutoff_ms = now_ms - self._settings.alert_cooldown_s * 1000
        expired = [
            key for key, ts in self._fingerprint_last_ms.items() if ts < cutoff_ms
        ]
        for key in expired:
            self._fingerprint_last_ms.pop(key, None)
            self._storage_checked.discard(key)
        if len(self._fingerprint_last_ms) > _FINGERPRINT_CACHE_MAX:
            # Oldest-first eviction. dict iteration preserves insertion
            # order, but last-write wins here — sort by value to be safe.
            to_evict = sorted(self._fingerprint_last_ms.items(), key=lambda kv: kv[1])[
                : len(self._fingerprint_last_ms) - _FINGERPRINT_CACHE_MAX
            ]
            for key, _ in to_evict:
                self._fingerprint_last_ms.pop(key, None)
                self._storage_checked.discard(key)

    @staticmethod
    def _dedupe_fingerprint(alert: Alert) -> tuple[str, ...]:
        """Build a dedupe key for semantically identical alerts."""
        fingerprint = [alert.alert_type, alert.coin]
        for key in ("address", "twap_id", "direction"):
            value = alert.metadata.get(key)
            if value is not None:
                fingerprint.append(f"{key}={value}")
        return tuple(fingerprint)

    def _is_throttled(self) -> bool:
        """Check if global alert rate limit is exceeded.

        Returns:
            True if too many alerts have been dispatched recently.
        """
        cutoff = time.monotonic() - 60.0
        # Prune expired entries from the left (deque is chronological)
        while self._dispatch_times and self._dispatch_times[0] < cutoff:
            self._dispatch_times.popleft()
        return len(self._dispatch_times) >= self._settings.alert_max_per_minute
