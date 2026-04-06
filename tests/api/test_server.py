"""Tests for API server startup helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.api.server import _ensure_db_ready


def test_ensure_db_ready_creates_schema(tmp_path: Path) -> None:
    """The API startup helper must create the DB file and tables eagerly."""
    db_path = tmp_path / "fresh.db"

    _ensure_db_ready(str(db_path))

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
