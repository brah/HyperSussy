"""Shared protocol definitions decoupled from any UI framework."""

from __future__ import annotations

from typing import Protocol

from hypersussy.models import AssetSnapshot


class DataBus(Protocol):
    """Interface for pushing live data into a display layer.

    Implemented by :class:`hypersussy.app.state.SharedState`. Passed
    into :class:`hypersussy.orchestrator.Orchestrator` so it can emit
    live events without importing framework-specific types.

    Every method the orchestrator calls through this interface is
    declared here — an earlier version omitted the error-reporting
    methods and forced the orchestrator to feature-sniff with
    ``getattr``. Reject that pattern: if a method is part of the
    contract, put it in the protocol.
    """

    def push_snapshot(self, snapshot: AssetSnapshot) -> None:
        """Push an asset snapshot into the display layer.

        Args:
            snapshot: The asset snapshot to display.
        """
        ...

    def mark_engine_error(self, engine_name: str, error: str) -> None:
        """Record the latest error for an engine.

        Args:
            engine_name: Engine that raised the error.
            error: Stringified exception message.
        """
        ...

    def clear_engine_error(self, engine_name: str) -> None:
        """Clear a previously recorded engine error.

        Args:
            engine_name: Engine whose error banner should be cleared.
        """
        ...

    def mark_runtime_error(self, source: str, error: str) -> None:
        """Record a runtime-loop error for UI visibility.

        Args:
            source: Logical loop name (e.g. ``"poll_meta"``).
            error: Stringified exception message.
        """
        ...

    def clear_runtime_error(self, source: str) -> None:
        """Clear a previously recorded runtime error.

        Args:
            source: Logical loop name that recovered.
        """
        ...
