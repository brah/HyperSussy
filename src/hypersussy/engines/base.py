"""Base protocol for detection engines."""

from __future__ import annotations

from typing import Protocol

from hypersussy.models import Alert, AssetSnapshot, Trade


class DetectionEngine(Protocol):
    """Interface that all detection engines implement.

    Not every engine needs to implement every method. The orchestrator
    calls each method and engines return empty lists when they have
    nothing to report for that event type.
    """

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        ...

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Called periodically by the orchestrator.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Any alerts generated during this tick.
        """
        ...

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Called in real-time for each incoming trade.

        Args:
            trade: The incoming trade.

        Returns:
            Any alerts generated from this trade.
        """
        ...

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Called when asset context updates arrive.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Any alerts generated from this update.
        """
        ...
