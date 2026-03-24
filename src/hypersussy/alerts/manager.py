"""Alert manager with deduplication, throttling, and dispatch."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence

from hypersussy.alerts.base import AlertSink
from hypersussy.config import HyperSussySettings
from hypersussy.models import Alert
from hypersussy.storage.base import StorageProtocol


class AlertManager:
    """Processes alerts through dedup, throttle, then dispatch.

    Args:
        storage: Storage backend for dedup queries.
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
        # Global throttle: timestamps of recent dispatches
        self._dispatch_times: deque[float] = deque(maxlen=1000)

    async def process_alert(self, alert: Alert) -> bool:
        """Deduplicate, throttle, persist, then dispatch an alert.

        Args:
            alert: The alert to process.

        Returns:
            True if the alert was dispatched, False if suppressed.
        """
        if await self._is_duplicate(alert):
            return False

        if self._is_throttled():
            return False

        await self._storage.insert_alert(alert)
        self._dispatch_times.append(time.monotonic())

        for sink in self._sinks:
            await sink.send(alert)

        return True

    async def _is_duplicate(self, alert: Alert) -> bool:
        """Check if a similar alert was recently fired.

        Args:
            alert: The alert to check.

        Returns:
            True if a duplicate exists within the cooldown window.
        """
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        since_ms = alert.timestamp_ms - cooldown_ms
        recent = await self._storage.get_recent_alerts(
            alert.alert_type, alert.coin, since_ms
        )
        return len(recent) > 0

    def _is_throttled(self) -> bool:
        """Check if global alert rate limit is exceeded.

        Returns:
            True if too many alerts have been dispatched recently.
        """
        now = time.monotonic()
        cutoff = now - 60.0
        # Count dispatches in the last minute
        recent_count = sum(1 for t in self._dispatch_times if t >= cutoff)
        return recent_count >= self._settings.alert_max_per_minute
