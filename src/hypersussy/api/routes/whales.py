"""GET/POST/DELETE /api/whales/* — tracked whale address management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import ActionsDep, PnlServiceDep, ReaderDep
from hypersussy.api.schemas import (
    AddWhaleRequest,
    CoinPositionItem,
    FillItem,
    FillPageResponse,
    PositionItem,
    RealizedPnlResponse,
    TrackedAddressItem,
    WhaleCountResponse,
)
from hypersussy.app.navigation import normalize_wallet_address

router = APIRouter(prefix="/whales", tags=["whales"])


@router.get("")
def get_whales(
    reader: ReaderDep,
    limit: int = Query(50, ge=1, le=500),
) -> list[TrackedAddressItem]:
    """Return tracked whale addresses ordered by total volume.

    Args:
        reader: Injected DashboardReader.
        limit: Maximum addresses to return (1–500).

    Returns:
        List of tracked address rows.
    """
    return [
        TrackedAddressItem.model_validate(r)
        for r in reader.get_tracked_addresses(limit=limit)
    ]


@router.get("/count")
def get_whale_count(reader: ReaderDep) -> WhaleCountResponse:
    """Return the total number of tracked addresses.

    Args:
        reader: Injected DashboardReader.

    Returns:
        WhaleCountResponse with the total count.
    """
    return WhaleCountResponse(count=reader.get_tracked_address_count())


@router.get("/positions/{address}")
def get_whale_positions(
    address: str,
    reader: ReaderDep,
) -> list[PositionItem]:
    """Return latest open positions for a whale address.

    Args:
        address: The 0x wallet address (42-char hex).
        reader: Injected DashboardReader.

    Returns:
        List of position rows ordered by notional descending.

    Raises:
        HTTPException: 422 if address is not a valid 0x wallet address.
    """
    addr = normalize_wallet_address(address)
    if addr is None:
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    return [
        PositionItem.model_validate(r) for r in reader.get_whale_positions(address=addr)
    ]


@router.get("/top/{coin}")
def get_top_coin_positions(
    coin: str,
    reader: ReaderDep,
    limit: int = Query(25, ge=1, le=100),
) -> list[CoinPositionItem]:
    """Return current open positions for the top tracked addresses in a coin.

    Results are timeframe-independent — always reflects the latest snapshot
    per address with a non-zero position, ordered by absolute notional descending.

    Args:
        coin: Asset ticker symbol (e.g. "BTC").
        reader: Injected DashboardReader.
        limit: Maximum positions to return (1–100).

    Returns:
        List of CoinPositionItem ordered by |notional_usd| descending.
    """
    return [
        CoinPositionItem.model_validate(r)
        for r in reader.get_top_coin_positions(coin=coin, limit=limit)
    ]


@router.get("/pnl/{address}")
async def get_realized_pnl(
    address: str,
    pnl_service: PnlServiceDep,
) -> RealizedPnlResponse:
    """Return realized PnL for a wallet (7-day and all-time).

    Fetches fill history from the Hyperliquid API and sums
    the ``closedPnl`` field across all fills.

    Args:
        address: The 0x wallet address (42-char hex).
        pnl_service: Injected PnL service.

    Returns:
        RealizedPnlResponse with 7-day and all-time totals.

    Raises:
        HTTPException: 422 if address is not a valid 0x wallet address.
    """
    addr = normalize_wallet_address(address)
    if addr is None:
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    snapshot = await pnl_service.get_pnl(addr)
    return RealizedPnlResponse(
        pnl_7d=snapshot.pnl_7d.realized_pnl,
        pnl_all_time=snapshot.pnl_all_time.realized_pnl,
        fills_7d=snapshot.pnl_7d.fill_count,
        fills_all_time=snapshot.pnl_all_time.fill_count,
        is_complete_7d=snapshot.pnl_7d.is_complete,
        is_complete_all_time=snapshot.pnl_all_time.is_complete,
    )


@router.get("/fills/{address}")
async def get_fills(
    address: str,
    pnl_service: PnlServiceDep,
    before_ms: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> FillPageResponse:
    """Return paginated fill history for a wallet from the HL API.

    Cursor-based backward pagination: pass ``before_ms`` from the
    previous response's ``next_cursor`` to load older fills.

    Args:
        address: The 0x wallet address (42-char hex).
        pnl_service: Injected PnL service.
        before_ms: Only fills before this timestamp (cursor).
        limit: Page size (1-200).

    Returns:
        FillPageResponse with fills and next_cursor.

    Raises:
        HTTPException: 422 if address is not a valid 0x wallet address.
    """
    addr = normalize_wallet_address(address)
    if addr is None:
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    fills, next_cursor = await pnl_service.get_fills(
        addr,
        before_ms=before_ms,
        limit=limit,
    )
    return FillPageResponse(
        fills=[FillItem.model_validate(f) for f in fills],
        next_cursor=next_cursor,
    )


@router.post("", status_code=201)
def add_whale(body: AddWhaleRequest, actions: ActionsDep) -> dict[str, str]:
    """Add a wallet address to the tracked list.

    Args:
        body: AddWhaleRequest with address and optional label.
        actions: Injected DashboardActions.

    Returns:
        Confirmation dict with the normalised address.

    Raises:
        HTTPException: 422 if address is not a valid 0x wallet address.
    """
    addr = normalize_wallet_address(body.address)
    if addr is None:
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    actions.add_tracked_address(address=addr, label=body.label)
    return {"address": addr}


@router.delete("/{address}", status_code=204)
def remove_whale(address: str, actions: ActionsDep) -> None:
    """Remove a wallet address from the tracked list.

    Args:
        address: The 0x wallet address (42-char hex).
        actions: Injected DashboardActions.

    Raises:
        HTTPException: 422 if address is not a valid 0x wallet address.
    """
    addr = normalize_wallet_address(address)
    if addr is None:
        raise HTTPException(status_code=422, detail="Invalid wallet address")
    actions.remove_tracked_address(address=addr)
