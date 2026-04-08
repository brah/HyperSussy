"""GET /api/alerts/* — alert list, counts, and by-address endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from hypersussy.api.deps import NormalizedAddressDep, ReaderDep
from hypersussy.api.schemas import AlertItem, AlertSummaryItem

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def get_alerts(
    reader: ReaderDep,
    limit: int = Query(200, ge=1, le=1000),
    since_ms: int = Query(0, ge=0),
) -> list[AlertItem]:
    """Return recent alerts ordered newest-first.

    Args:
        reader: Injected DashboardReader.
        limit: Maximum rows to return (1–1000).
        since_ms: Only return alerts after this Unix-ms timestamp.

    Returns:
        List of alert rows.
    """
    return [
        AlertItem.model_validate(r)
        for r in reader.get_alerts_all(limit=limit, since_ms=since_ms)
    ]


@router.get("/counts")
def get_alert_counts(
    reader: ReaderDep,
    since_ms: int = Query(0, ge=0),
) -> dict[str, int]:
    """Return count of alerts per engine type.

    Args:
        reader: Injected DashboardReader.
        since_ms: Only count alerts after this Unix-ms timestamp.

    Returns:
        Mapping of alert_type to count.
    """
    return reader.get_alert_counts_by_type(since_ms=since_ms)


@router.get("/by-address/{address}")
def get_alerts_by_address(
    address: NormalizedAddressDep,
    reader: ReaderDep,
    limit: int = Query(20, ge=1, le=200),
) -> list[AlertSummaryItem]:
    """Return alerts associated with a wallet address.

    Args:
        address: The 0x wallet address (42-char hex), normalised by
            the FastAPI dependency.
        reader: Injected DashboardReader.
        limit: Maximum alerts to return (1–200).

    Returns:
        List of condensed alert rows ordered newest-first.
    """
    return [
        AlertSummaryItem.model_validate(r)
        for r in reader.get_alerts_by_address(address=address, limit=limit)
    ]
