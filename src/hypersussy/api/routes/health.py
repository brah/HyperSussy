"""GET /api/health — runtime health check."""

from __future__ import annotations

import io
import os

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from hypersussy.api.deps import StateDep
from hypersussy.api.schemas import HealthResponse, RuntimeIssueItem

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health(state: StateDep) -> HealthResponse:
    """Return current orchestrator health.

    Args:
        state: Injected SharedState.

    Returns:
        HealthResponse with running flag, snapshot counts, and errors.
    """
    health = state.get_runtime_health()
    return HealthResponse(
        is_running=health.is_running,
        snapshot_count=health.snapshot_count,
        last_snapshot_ms=health.last_snapshot_ms,
        last_alert_ms=health.last_alert_ms,
        engine_errors=[
            RuntimeIssueItem(
                source=i.source,
                message=i.message,
                timestamp_ms=i.timestamp_ms,
            )
            for i in health.engine_errors
        ],
        runtime_errors=[
            RuntimeIssueItem(
                source=i.source,
                message=i.message,
                timestamp_ms=i.timestamp_ms,
            )
            for i in health.runtime_errors
        ],
    )


@router.get("/health/logs", response_class=PlainTextResponse)
def get_logs(
    state: StateDep,
    lines: int = Query(500, ge=1, le=5000),
) -> str:
    """Return the tail of the background runner's log file.

    Args:
        state: Injected SharedState.
        lines: Maximum number of tail lines to return (1–5000).

    Returns:
        Plain-text log content, or an explanatory message if unavailable.
    """
    path = state.get_log_path()
    if path is None:
        return "Log file path not yet set (runner may not have started)."
    if not os.path.isfile(path):
        return f"Log file not found: {path}"
    return _tail_file(path, lines)


def _tail_file(path: str, lines: int) -> str:
    """Read the last *lines* lines from a file efficiently.

    Seeks backwards from the end in growing chunks, avoiding the cost
    of reading the entire file into memory on every request.

    Args:
        path: Filesystem path to the log file.
        lines: Number of tail lines to return.

    Returns:
        The last *lines* lines as a single string.
    """
    with open(path, "rb") as fh:
        fh.seek(0, io.SEEK_END)
        file_size = fh.tell()
        if file_size == 0:
            return ""

        chunk_size = 8192
        found_lines = 0
        position = file_size
        buf = b""

        while position > 0 and found_lines <= lines:
            read_size = min(chunk_size, position)
            position -= read_size
            fh.seek(position)
            buf = fh.read(read_size) + buf
            found_lines = buf.count(b"\n")

    text = buf.decode("utf-8", errors="replace")
    tail = text.splitlines(keepends=True)
    return "".join(tail[-lines:])
