"""GET /api/health — runtime health check."""

from __future__ import annotations

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
    with open(path, encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()
    return "".join(all_lines[-lines:])
