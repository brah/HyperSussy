"""TUI alert sink that forwards alerts into the Textual event bus."""

from __future__ import annotations

from hypersussy.models import Alert
from hypersussy.protocols import DataBus


class TuiSink:
    """Alert sink that pushes alerts into the TUI via the DataBus.

    Implements the AlertSink protocol. Designed to run alongside LogSink
    so structured file logging is preserved while the TUI displays alerts.

    Args:
        data_bus: The DataBus implementor (HyperSussyApp instance).
    """

    def __init__(self, data_bus: DataBus) -> None:
        self._bus = data_bus

    async def send(self, alert: Alert) -> None:
        """Forward the alert to the TUI event bus.

        Args:
            alert: The alert to display in the TUI.
        """
        self._bus.push_alert(alert)
