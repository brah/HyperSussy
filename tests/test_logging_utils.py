"""Tests for LogFloodGuard suppression and pruning."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from hypersussy.logging_utils import LogFloodGuard


class TestLogFloodGuardPruning:
    """Expired keys are pruned to prevent unbounded memory growth."""

    def test_expired_keys_pruned_after_interval(self) -> None:
        """Keys older than 2x the window are removed on prune sweeps."""
        guard = LogFloodGuard(window_s=1.0)
        mock_logger = MagicMock(spec=logging.Logger)

        # Inject many unique keys to trigger a prune cycle
        for i in range(guard._PRUNE_INTERVAL + 1):
            guard.log(mock_logger, logging.WARNING, f"key-{i}", "msg %d", i)

        # All keys should exist (still within window)
        assert len(guard._windows) > 0

        # Fast-forward time: make all keys appear expired
        import time

        fake_past = time.monotonic() - 10.0
        for window in guard._windows.values():
            window.started_at = fake_past

        # Trigger another prune cycle
        for i in range(guard._PRUNE_INTERVAL + 1):
            guard.log(
                mock_logger, logging.WARNING, f"new-key-{i}", "msg %d", i
            )

        # Old expired keys should be gone; only new keys remain
        old_keys = [k for k in guard._windows if k.startswith("key-")]
        assert len(old_keys) == 0

    def test_active_keys_not_pruned(self) -> None:
        """Keys within the suppression window survive prune sweeps."""
        guard = LogFloodGuard(window_s=60.0)
        mock_logger = MagicMock(spec=logging.Logger)

        guard.log(mock_logger, logging.WARNING, "active-key", "msg")
        assert "active-key" in guard._windows

        # Trigger prune by filling ops counter
        for i in range(guard._PRUNE_INTERVAL + 1):
            guard.log(mock_logger, logging.WARNING, f"filler-{i}", "msg")

        # The active key should still exist (within 60s window)
        assert "active-key" in guard._windows


class TestLogFloodGuardSuppression:
    """Basic suppression behavior (pre-existing, not new)."""

    def test_suppresses_duplicate_within_window(self) -> None:
        """Second identical key within window is suppressed."""
        guard = LogFloodGuard(window_s=60.0)
        mock_logger = MagicMock(spec=logging.Logger)

        first = guard.log(mock_logger, logging.WARNING, "dup", "msg")
        second = guard.log(mock_logger, logging.WARNING, "dup", "msg")

        assert first is True
        assert second is False
        assert mock_logger.log.call_count == 1
