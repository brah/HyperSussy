"""Shared test fixtures."""

from __future__ import annotations

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.storage.sqlite import SqliteStorage


@pytest.fixture
async def storage() -> SqliteStorage:
    """In-memory SQLite storage for tests."""
    store = SqliteStorage(db_path=":memory:")
    await store.init()
    yield store  # type: ignore[misc]
    await store.close()


@pytest.fixture
def settings() -> HyperSussySettings:
    """Default settings for tests."""
    return HyperSussySettings()
