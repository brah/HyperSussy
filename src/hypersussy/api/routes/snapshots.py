"""GET /api/snapshots/* — OI, funding, and coin list endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import ReaderDep, SettingsDep
from hypersussy.api.schemas import FundingSnapshotItem, OISnapshotItem
from hypersussy.config import HyperSussySettings

router = APIRouter(prefix="/snapshots", tags=["snapshots"])

# Upper bound passed to Pydantic at request-validation time. The
# real, dynamic cap derived from the live retention window is
# enforced inside each handler via ``_check_hours_against_retention``;
# this outer 720h (30d) ceiling just guards against runaway numeric
# inputs and matches the historical contract.
_HARD_MAX_HOURS = 720


def _max_snapshot_hours(settings: HyperSussySettings) -> int:
    """Return the effective max lookback window for snapshot queries.

    Bounded by the live ``asset_snapshots_retention_days`` setting so
    the endpoint never promises data it has already deleted. Falls
    back to the historical 30-day cap when retention is disabled.
    """
    days = settings.asset_snapshots_retention_days
    return days * 24 if days > 0 else _HARD_MAX_HOURS


def _check_snapshot_hours(hours: int, settings: HyperSussySettings) -> None:
    """Raise 422 if ``hours`` exceeds the live retention window."""
    cap = _max_snapshot_hours(settings)
    if hours > cap:
        raise HTTPException(
            status_code=422,
            detail=(
                f"hours={hours} exceeds asset_snapshots retention "
                f"window ({cap}h). Increase "
                f"asset_snapshots_retention_days to query further back."
            ),
        )


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
    settings: SettingsDep,
    hours: int = Query(24, ge=1, le=_HARD_MAX_HOURS),
) -> list[OISnapshotItem]:
    """Return open interest history for a coin.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        settings: Live settings (for the retention-window cap).
        hours: Lookback window. Capped at the live
            ``asset_snapshots_retention_days * 24``.

    Returns:
        List of OI snapshot rows ordered oldest-first.
    """
    _check_snapshot_hours(hours, settings)
    return [
        OISnapshotItem.model_validate(r)
        for r in reader.get_oi_history(coin=coin, hours=hours)
    ]


@router.get("/funding/{coin}")
def get_funding(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(24, ge=1, le=_HARD_MAX_HOURS),
) -> list[FundingSnapshotItem]:
    """Return funding rate history for a coin.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        settings: Live settings (for the retention-window cap).
        hours: Lookback window. Capped at the live
            ``asset_snapshots_retention_days * 24``.

    Returns:
        List of funding snapshot rows ordered oldest-first.
    """
    _check_snapshot_hours(hours, settings)
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
