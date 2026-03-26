"""GET /api/snapshots/* — OI, funding, and coin list endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from hypersussy.api.deps import ReaderDep
from hypersussy.api.schemas import FundingSnapshotItem, OISnapshotItem

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/coins")
def get_coins(reader: ReaderDep) -> list[str]:
    """Return distinct coin symbols present in the database.

    Args:
        reader: Injected DashboardReader.

    Returns:
        Sorted list of coin ticker strings.
    """
    return reader.get_distinct_coins()


@router.get("/oi/{coin}")
def get_oi(
    coin: str,
    reader: ReaderDep,
    hours: int = Query(24, ge=1, le=720),
) -> list[OISnapshotItem]:
    """Return open interest history for a coin.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        hours: Lookback window (1–720 hours).

    Returns:
        List of OI snapshot rows ordered oldest-first.
    """
    return [
        OISnapshotItem.model_validate(r)
        for r in reader.get_oi_history(coin=coin, hours=hours)
    ]


@router.get("/funding/{coin}")
def get_funding(
    coin: str,
    reader: ReaderDep,
    hours: int = Query(24, ge=1, le=720),
) -> list[FundingSnapshotItem]:
    """Return funding rate history for a coin.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        hours: Lookback window (1–720 hours).

    Returns:
        List of funding snapshot rows ordered oldest-first.
    """
    return [
        FundingSnapshotItem.model_validate(r)
        for r in reader.get_funding_history(coin=coin, hours=hours)
    ]


@router.get("/latest-oi")
def get_latest_oi(reader: ReaderDep) -> dict[str, float]:
    """Return the latest open interest (base units) per coin.

    Args:
        reader: Injected DashboardReader.

    Returns:
        Mapping of coin symbol to open interest value.
    """
    return reader.get_latest_oi_per_coin()
