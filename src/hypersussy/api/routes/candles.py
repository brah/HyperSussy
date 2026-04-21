"""GET /api/candles/{coin} -- cursor-paginated OHLCV candle data."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from hypersussy.api.deps import CandleServiceDep
from hypersussy.api.schemas import CandleItem

router = APIRouter(prefix="/candles", tags=["candles"])

_VALID_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})

# Frontends that haven't migrated to the cursor API still pass
# ``hours``; translate that to a bar count so both shapes work.
_INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


@router.get("/{coin}")
async def get_candles(
    coin: str,
    candle_service: CandleServiceDep,
    interval: str = Query("1h"),
    before_ms: int | None = Query(None, ge=0),
    limit: int | None = Query(None, ge=1, le=10_000),
    hours: int | None = Query(None, ge=1, le=87_600),
) -> list[CandleItem]:
    """Return OHLCV candles ending strictly before ``before_ms``.

    Cursor-based pagination: pass the ``timestamp_ms`` of the oldest
    bar on the previous page as ``before_ms`` to load older data.
    ``limit`` caps the number of bars returned per call; the service
    also backfills any missing older range from the Hyperliquid API
    transparently on cache miss.

    ``hours`` is kept as a convenience for the legacy path: when
    given (and ``limit`` is not), it's translated to a bar count so
    callers that haven't migrated still get a sensibly-sized page.

    Args:
        coin: Asset ticker symbol.
        candle_service: Injected fetch-through candle service.
        interval: Candle interval string (``1m``, ``5m``, ``15m``,
            ``1h``, ``4h``, ``1d``).
        before_ms: Exclusive upper bound on ``timestamp_ms`` (cursor).
            Omit for newest bars.
        limit: Maximum rows to return (1-10000). Omit to use the
            service default.
        hours: Legacy parameter — translated to ``limit`` when
            ``limit`` isn't supplied. Harmless to drop from new
            clients.

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

    effective_limit = limit
    if effective_limit is None and hours is not None:
        # Translate legacy ``hours`` into a bar count. Interval is
        # validated above so the dict lookup is safe.
        effective_limit = max(1, hours * 3_600_000 // _INTERVAL_MS[interval])

    rows = await candle_service.get_candle_page(
        coin=coin,
        interval=interval,
        before_ms=before_ms,
        limit=effective_limit,
    )
    return [CandleItem.model_validate(r) for r in rows]
