"""GET /api/trades/* — whale trades, top-holders, and flow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import ReaderDep, SettingsDep
from hypersussy.api.schemas import (
    TopHolderItem,
    TopWhaleItem,
    TradeFlowItem,
)
from hypersussy.config import HyperSussySettings

router = APIRouter(prefix="/trades", tags=["trades"])

_VALID_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}

# Outer ceiling for Pydantic validation; the real dynamic cap is
# derived from the live trades retention window and enforced inside
# each handler via ``_check_trades_hours``.
_HARD_MAX_HOURS = 720


def _max_trades_hours(settings: HyperSussySettings) -> int:
    """Return the effective max lookback window for trade queries."""
    days = settings.trades_retention_days
    return days * 24 if days > 0 else _HARD_MAX_HOURS


def _check_trades_hours(hours: int, settings: HyperSussySettings) -> None:
    """Raise 422 if ``hours`` exceeds the live trades retention window."""
    cap = _max_trades_hours(settings)
    if hours > cap:
        raise HTTPException(
            status_code=422,
            detail=(
                f"hours={hours} exceeds trades retention window "
                f"({cap}h). Increase trades_retention_days to query "
                f"further back."
            ),
        )


@router.get("/top-whales/{coin}")
def get_top_whales(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(1, ge=1, le=_HARD_MAX_HOURS),
) -> list[TopWhaleItem]:
    """Return top addresses by combined buy+sell volume for a coin.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        settings: Live settings (for the retention-window cap).
        hours: Lookback window. Capped at the live
            ``trades_retention_days * 24``.

    Returns:
        List of address + volume rows ordered by volume descending.
    """
    _check_trades_hours(hours, settings)
    return [
        TopWhaleItem.model_validate(r)
        for r in reader.get_top_whales(coin=coin, hours=hours)
    ]


@router.get("/top-holders/{coin}")
def get_top_holders(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(24, ge=1, le=_HARD_MAX_HOURS),
    limit: int = Query(15, ge=1, le=50),
) -> list[TopHolderItem]:
    """Return top addresses by volume with market-total context.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        settings: Live settings (for the retention-window cap).
        hours: Lookback window. Capped at the live
            ``trades_retention_days * 24``.
        limit: Maximum addresses to return (1–50).

    Returns:
        List of address + volume + total_volume rows.
    """
    _check_trades_hours(hours, settings)
    return [
        TopHolderItem.model_validate(r)
        for r in reader.get_top_holders_concentration(
            coin=coin, hours=hours, limit=limit
        )
    ]


@router.get("/flow/{coin}")
def get_trade_flow(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(24, ge=1, le=_HARD_MAX_HOURS),
) -> list[TradeFlowItem]:
    """Return buy vs sell volume bucketed by hour.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        settings: Live settings (for the retention-window cap).
        hours: Lookback window. Capped at the live
            ``trades_retention_days * 24``.

    Returns:
        List of (bucket_ms, side, volume_usd) rows ordered oldest-first.
    """
    _check_trades_hours(hours, settings)
    return [
        TradeFlowItem.model_validate(r)
        for r in reader.get_trade_flow_by_hour(coin=coin, hours=hours)
    ]
