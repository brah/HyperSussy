"""GET /api/health — runtime health check."""

from __future__ import annotations

from fastapi import APIRouter

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
