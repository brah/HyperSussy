"""Fetch-through candle cache backed by the Hyperliquid REST API.

On each request the service checks the local SQLite cache first.  If the
newest cached candle is stale (older than two interval periods) it fetches
fresh data from the HL API, upserts into the DB, and returns the result.
"""

from __future__ import annotations

import logging
import time

import aiosqlite
import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.rate_limiter import WeightRateLimiter

logger = logging.getLogger(__name__)

_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

_UPSERT_SQL = """
INSERT OR REPLACE INTO candles
    (coin, interval_str, timestamp_ms, open, high, low, close, volume, num_trades)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_SQL = """
SELECT timestamp_ms, open, high, low, close, volume, num_trades
FROM candles
WHERE coin = ? AND interval_str = ? AND timestamp_ms >= ?
ORDER BY timestamp_ms ASC
"""

_RANGE_SQL = """
SELECT MIN(timestamp_ms), MAX(timestamp_ms) FROM candles
WHERE coin = ? AND interval_str = ? AND timestamp_ms >= ?
"""


class CandleService:
    """Async fetch-through candle cache.

    Args:
        base_url: Hyperliquid API base URL.
        db_path: Path to the SQLite database file.
        rate_limit_weight: Max API weight budget for candle fetches.
        window_seconds: Rate limiter sliding window duration.
    """

    def __init__(
        self,
        base_url: str,
        db_path: str,
        rate_limit_weight: int = 200,
        window_seconds: int = 60,
    ) -> None:
        limiter = WeightRateLimiter(
            max_weight=rate_limit_weight,
            window_seconds=window_seconds,
        )
        self._reader = HyperLiquidReader(
            base_url=base_url,
            rate_limiter=limiter,
        )
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open the async SQLite connection with WAL mode."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get_candles(
        self,
        coin: str,
        interval: str,
        hours: int,
    ) -> list[dict[str, object]]:
        """Return OHLCV candles, fetching from HL API if the cache is stale.

        Args:
            coin: Asset ticker symbol.
            interval: Candle interval (e.g. ``1m``, ``1h``).
            hours: Lookback window in hours.

        Returns:
            List of candle dicts ordered oldest-first.
        """
        assert self._db is not None  # noqa: S101
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - hours * 3_600_000
        interval_ms = _INTERVAL_MS[interval]

        # Only use cache when it is fresh and spans the requested lookback.
        async with self._db.execute(_RANGE_SQL, (coin, interval, start_ms)) as cursor:
            row = await cursor.fetchone()
        min_ts: int | None = row[0] if row and row[0] is not None else None
        max_ts: int | None = row[1] if row and row[1] is not None else None
        covers_window = min_ts is not None and min_ts <= start_ms + interval_ms

        if (
            max_ts is not None
            and covers_window
            and (now_ms - max_ts) < 2 * interval_ms
        ):
            return await self._read_cached(coin, interval, start_ms)

        # Cache miss or stale -- fetch from HL API
        try:
            candles = await self._reader.get_candles(
                coin=coin,
                interval=interval,
                start_ms=start_ms,
                end_ms=now_ms,
            )
        except (ClientError, ServerError, requests.RequestException, OSError):
            logger.error(
                "HL candle fetch failed for %s (%s); falling back to cache",
                coin,
                interval,
                exc_info=True,
            )
            return await self._read_cached(coin, interval, start_ms)

        if candles:
            params = [
                (
                    c.coin,
                    c.interval,
                    c.timestamp_ms,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                    c.num_trades,
                )
                for c in candles
            ]
            await self._db.executemany(_UPSERT_SQL, params)
            await self._db.commit()

        return [
            {
                "timestamp_ms": c.timestamp_ms,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "num_trades": c.num_trades,
            }
            for c in candles
        ]

    async def _read_cached(
        self,
        coin: str,
        interval: str,
        start_ms: int,
    ) -> list[dict[str, object]]:
        """Read candles from the SQLite cache.

        Args:
            coin: Asset ticker symbol.
            interval: Candle interval string.
            start_ms: Earliest timestamp in milliseconds.

        Returns:
            List of candle dicts ordered oldest-first.
        """
        assert self._db is not None  # noqa: S101
        async with self._db.execute(_SELECT_SQL, (coin, interval, start_ms)) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "timestamp_ms": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
                "num_trades": r[6],
            }
            for r in rows
        ]
