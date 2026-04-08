"""GET /api/trades/* — whale trades, top-holders, and flow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from hypersussy.api.deps import ReaderDep, SettingsDep
from hypersussy.api.routes._retention_window import (
    HARD_MAX_HOURS,
    check_hours_within_retention,
)
from hypersussy.api.schemas import (
    TopHolderItem,
    TopWhaleItem,
    TradeFlowItem,
)

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/top-whales/{coin}")
def get_top_whales(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(1, ge=1, le=HARD_MAX_HOURS),
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
    check_hours_within_retention(
        hours,
        settings,
        days_field="trades_retention_days",
        label="trades",
    )
    return [
        TopWhaleItem.model_validate(r)
        for r in reader.get_top_whales(coin=coin, hours=hours)
    ]


@router.get("/top-holders/{coin}")
def get_top_holders(
    coin: str,
    reader: ReaderDep,
    settings: SettingsDep,
    hours: int = Query(24, ge=1, le=HARD_MAX_HOURS),
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
    check_hours_within_retention(
        hours,
        settings,
        days_field="trades_retention_days",
        label="trades",
    )
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
    hours: int = Query(24, ge=1, le=HARD_MAX_HOURS),
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
    check_hours_within_retention(
        hours,
        settings,
        days_field="trades_retention_days",
        label="trades",
    )
    return [
        TradeFlowItem.model_validate(r)
        for r in reader.get_trade_flow_by_hour(coin=coin, hours=hours)
    ]
