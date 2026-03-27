"""Tests for dashboard write actions."""

from __future__ import annotations

import importlib.resources
import sqlite3
import time
from pathlib import Path

import pytest

from hypersussy.app.actions import DashboardActions


@pytest.fixture
def db_path() -> str:
    """Create a local SQLite database with the real schema."""
    path = Path(f"dashboard_actions_test_{time.time_ns()}.db")
    schema_sql = (
        importlib.resources.files("hypersussy.storage")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(path)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)


def test_add_tracked_address_inserts_manual_row(db_path: str) -> None:
    """Manual add writes a tracked address row with manual source."""
    actions = DashboardActions(db_path)
    actions.add_tracked_address("0x1111111111111111111111111111111111111111", "MANUAL")
    actions.close()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT label, source, is_manual FROM tracked_addresses WHERE address = ?",
        ("0x1111111111111111111111111111111111111111",),
    ).fetchone()
    conn.close()
    assert row == ("MANUAL", "manual", 1)


def test_remove_tracked_address_deletes_row(db_path: str) -> None:
    """Remove deletes the tracked address row."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO tracked_addresses
           (address, label, source, first_seen_ms, total_volume_usd, last_active_ms)
           VALUES (?, 'test', 'manual', 1, 0.0, 1)""",
        ("0x2222222222222222222222222222222222222222",),
    )
    conn.commit()
    conn.close()

    actions = DashboardActions(db_path)
    actions.remove_tracked_address("0x2222222222222222222222222222222222222222")
    actions.close()

    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM tracked_addresses WHERE address = ?",
        ("0x2222222222222222222222222222222222222222",),
    ).fetchone()[0]
    conn.close()
    assert count == 0
