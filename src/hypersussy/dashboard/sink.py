"""Streamlit alert sink that forwards alerts into SharedState."""

from __future__ import annotations

from hypersussy.dashboard.state import SharedState
from hypersussy.models import Alert


class StreamlitSink:
    """Alert sink that pushes alerts into SharedState for Streamlit consumption.

    Implements the AlertSink protocol.

    Args:
        state: The shared state object to push alerts into.
    """

    def __init__(self, state: SharedState) -> None:
        self._state = state

    async def send(self, alert: Alert) -> None:
        """Push the alert into shared state.

        Args:
            alert: The alert to forward.
        """
        self._state.push_alert(alert)
