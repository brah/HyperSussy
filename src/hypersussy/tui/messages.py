"""Custom Textual messages and the DataBus protocol for TUI data flow.

The DataBus protocol is defined in hypersussy.protocols and re-exported
here for backward compatibility. The Textual Message subclasses are used
for intra-app event routing within the TUI.
"""

from __future__ import annotations

from textual.message import Message

from hypersussy.models import Alert, AssetSnapshot
from hypersussy.protocols import DataBus

__all__ = ["AlertReceived", "DataBus", "SnapshotUpdated"]


class SnapshotUpdated(Message):
    """Posted when a new AssetSnapshot arrives from the orchestrator.

    Args:
        snapshot: The updated asset snapshot.
    """

    def __init__(self, snapshot: AssetSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot


class AlertReceived(Message):
    """Posted when an Alert passes through the AlertManager pipeline.

    Args:
        alert: The dispatched alert.
    """

    def __init__(self, alert: Alert) -> None:
        super().__init__()
        self.alert = alert
