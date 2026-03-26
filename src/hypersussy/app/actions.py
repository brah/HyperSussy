"""Mutation-oriented SQLite actions for API endpoints."""

from __future__ import annotations

import sqlite3
import time


class DashboardActions:
    """Writable SQLite interface for API-triggered actions."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA busy_timeout=5000")

    def add_tracked_address(self, address: str, label: str | None) -> None:
        """Manually add a whale address for tracking."""
        now_ms = int(time.time() * 1000)
        self._conn.execute(
            """INSERT OR IGNORE INTO tracked_addresses
               (address, label, source, first_seen_ms,
                total_volume_usd, last_active_ms, is_manual)
               VALUES (?, ?, 'manual', ?, 0.0, ?, 1)""",
            (address, label or "", now_ms, now_ms),
        )
        self._conn.commit()

    def remove_tracked_address(self, address: str) -> None:
        """Remove a tracked whale address."""
        self._conn.execute("DELETE FROM tracked_addresses WHERE address = ?", (address,))
        self._conn.commit()

    def close(self) -> None:
        """Close the writable connection."""
        self._conn.close()
