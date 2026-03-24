"""Shared protocol definitions decoupled from any UI framework."""

from __future__ import annotations

from typing import Protocol

from hypersussy.models import Alert, AssetSnapshot


class DataBus(Protocol):
    """Interface for pushing live data into a display layer.

    Implemented by HyperSussyApp (TUI) and SharedState (Streamlit dashboard).
    Passed into Orchestrator and alert sinks so they can emit events without
    importing framework-specific types.
    """

    def push_snapshot(self, snapshot: AssetSnapshot) -> None:
        """Push an asset snapshot into the display layer.

        Args:
            snapshot: The asset snapshot to display.
        """
        ...

    def push_alert(self, alert: Alert) -> None:
        """Push an alert into the display layer.

        Args:
            alert: The alert to display.
        """
        ...
