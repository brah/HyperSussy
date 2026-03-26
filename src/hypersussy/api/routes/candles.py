"""GET /api/candles/{coin} -- OHLCV candle data."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import CandleServiceDep
from hypersussy.api.schemas import CandleItem

router = APIRouter(prefix="/candles", tags=["candles"])

_VALID_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


@router.get("/{coin}")
async def get_candles(
    coin: str,
    candle_service: CandleServiceDep,
    interval: str = Query("1h"),
    hours: int = Query(48, ge=1, le=2160),
) -> list[CandleItem]:
    """Return OHLCV candles for a coin and interval.

    Fetches from the Hyperliquid REST API with a transparent SQLite cache.
    Subsequent requests within two interval periods are served from cache.

    Args:
        coin: Asset ticker symbol.
        candle_service: Injected fetch-through candle service.
        interval: Candle interval string (``1m``, ``5m``, ``15m``, ``1h``,
            ``4h``, ``1d``).
        hours: Lookback window (1-2160 hours).

    Returns:
        List of candle rows ordered oldest-first.

    Raises:
        HTTPException: 422 if interval is not a recognised value.
    """
    if interval not in _VALID_INTERVALS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid interval '{interval}'. Must be one of: "
            + ", ".join(sorted(_VALID_INTERVALS)),
        )
    rows = await candle_service.get_candles(
        coin=coin,
        interval=interval,
        hours=hours,
    )
    return [CandleItem.model_validate(r) for r in rows]
