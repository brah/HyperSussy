"""Alert sink that puts alerts into the shared state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypersussy.alerts.base import AlertSink

if TYPE_CHECKING:
    from hypersussy.app.state import SharedState
    from hypersussy.models import Alert


class AppSink(AlertSink):
    """An alert sink that adds alerts to the shared state."""

    def __init__(self, state: SharedState) -> None:
        self.state = state

    async def send(self, alert: Alert) -> None:
        """Add the alert to the shared state."""
        self.state.push_alert(alert)

