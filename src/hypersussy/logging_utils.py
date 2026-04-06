"""Helpers for suppressing repeated identical log events."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _SuppressionWindow:
    """Mutable suppression state for one logical log key."""

    started_at: float
    suppressed: int = 0


class LogFloodGuard:
    """Allow one log per key per window and summarize suppressed repeats.

    This is intentionally tiny and dependency-free so it can be used in
    hot paths such as trade ingestion and REST retry loops.

    Expired keys are pruned periodically to prevent unbounded memory
    growth in long-running processes that encounter many unique keys.
    """

    _PRUNE_INTERVAL = 256  # check count between prune sweeps

    def __init__(self, window_s: float = 30.0) -> None:
        self._window_s = window_s
        self._windows: dict[str, _SuppressionWindow] = {}
        self._lock = threading.Lock()
        self._ops_since_prune = 0

    def log(
        self,
        logger: logging.Logger,
        level: int,
        key: str,
        message: str,
        *args: object,
        **kwargs: Any,
    ) -> bool:
        """Emit a log event unless an identical key was logged recently.

        Returns:
            True if a log line was emitted, False if suppressed.
        """
        emit, suppressed = self._should_emit(key)
        if not emit:
            return False
        if suppressed > 0:
            message = (
                f"{message} [suppressed {suppressed} similar event(s)"
                f" in last {int(self._window_s)}s]"
            )
        logger.log(level, message, *args, **kwargs)
        return True

    def _should_emit(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            self._ops_since_prune += 1
            if self._ops_since_prune >= self._PRUNE_INTERVAL:
                self._prune_expired(now)
                self._ops_since_prune = 0

            window = self._windows.get(key)
            if window is None:
                self._windows[key] = _SuppressionWindow(started_at=now)
                return True, 0
            if now - window.started_at >= self._window_s:
                suppressed = window.suppressed
                window.started_at = now
                window.suppressed = 0
                return True, suppressed
            window.suppressed += 1
            return False, 0

    def _prune_expired(self, now: float) -> None:
        """Remove keys whose suppression window has fully elapsed.

        Must be called while holding ``self._lock``.
        """
        # Use 2x window so we don't prune keys that are about to emit
        # their suppression summary.
        cutoff = now - self._window_s * 2
        expired = [k for k, w in self._windows.items() if w.started_at < cutoff]
        for k in expired:
            del self._windows[k]
