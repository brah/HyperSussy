"""Tests for API server startup helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.storage.sqlite import SqliteStorage


async def test_storage_init_creates_schema(tmp_path: Path) -> None:
    """Opening and initialising SqliteStorage creates the schema.

    The API lifespan relies on ``config_storage.init()`` to create
    the schema so the read-only ``DashboardReader`` can connect.
    Regression test for that ordering — an earlier version of the
    server ran a separate synchronous helper; this test pins the
    contract that ``SqliteStorage.init()`` alone is sufficient.
    """
    db_path = tmp_path / "fresh.db"
    storage = SqliteStorage(db_path=str(db_path))
    await storage.init()
    await storage.close()

    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"asset_snapshots", "trades", "tracked_addresses", "alerts"} <= tables
