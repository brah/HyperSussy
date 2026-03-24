"""Alert sink protocol for dispatching alerts."""

from __future__ import annotations

from typing import Protocol

from hypersussy.models import Alert


class AlertSink(Protocol):
    """Interface for alert delivery backends."""

    async def send(self, alert: Alert) -> None:
        """Dispatch an alert to the sink.

        Args:
            alert: The alert to deliver.
        """
        ...
