"""Shared exception-category tuples for the orchestrator and runner.

Callers pattern-match against these in ``try: ... except RECOVERABLE``
blocks. The split matters because:

* ``NETWORK_ERRORS`` are transient infrastructure failures where a
  retry or backoff is the appropriate response.
* ``LOGIC_ERRORS`` indicate programming or data bugs that should
  ideally be investigated, but are caught to keep the daemon alive
  instead of letting a single bad payload crash the event loop.

Promoting these to a module lets the orchestrator and the
``BackgroundRunner`` agree on one definition instead of maintaining
two near-duplicate tuples that silently drift apart.
"""

from __future__ import annotations

import sqlite3

import requests
from hyperliquid.utils.error import ClientError, ServerError

NETWORK_ERRORS: tuple[type[Exception], ...] = (
    ClientError,
    ServerError,
    requests.RequestException,
    sqlite3.Error,
    OSError,
)

LOGIC_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    TypeError,
    # ``RuntimeError`` covers ``aiosqlite``'s "loop is closed" and the
    # handful of places where callers wrap unexpected paths in a
    # ``RuntimeError``. Including it here keeps the runner and the
    # orchestrator in agreement about what counts as "caught but
    # worth investigating" — before this module existed, only the
    # runner caught RuntimeError.
    RuntimeError,
)

RECOVERABLE: tuple[type[Exception], ...] = NETWORK_ERRORS + LOGIC_ERRORS
