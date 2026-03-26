"""GET /api/candles/{coin} — OHLCV candle data."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import ReaderDep
from hypersussy.api.schemas import CandleItem

router = APIRouter(prefix="/candles", tags=["candles"])

_VALID_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


@router.get("/{coin}")
def get_candles(
    coin: str,
    reader: ReaderDep,
    interval: str = Query("1h"),
    hours: int = Query(48, ge=1, le=720),
) -> list[CandleItem]:
    """Return OHLCV candles for a coin and interval.

    Args:
        coin: Asset ticker symbol.
        reader: Injected DashboardReader.
        interval: Candle interval string (``1m``, ``5m``, ``15m``, ``1h``,
            ``4h``, ``1d``).
        hours: Lookback window (1–720 hours).

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
    return [
        CandleItem.model_validate(r)
        for r in reader.get_candles(coin=coin, interval=interval, hours=hours)
    ]
