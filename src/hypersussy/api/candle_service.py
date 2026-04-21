"""Cursor-paginated candle cache backed by the Hyperliquid REST API.

The service exposes one public entry point, :meth:`get_candle_page`,
which returns up to ``limit`` bars strictly before a cursor
timestamp. Two invariants support the frontend's pan-to-load
pagination:

* Every requested range is backfilled from HL on cache miss (up to
  HL's per-request cap, repeated until the target range is covered
  or the exchange stops returning bars).
* Initial loads (``before_ms=None``) top up the newest end of the
  range when the cache is older than two interval periods.

The cache never evicts candles; it grows monotonically. Row size is
~50 bytes so 5000 bars × 6 intervals × 200 coins ≈ 300 MB worst
case — well within SQLite's comfort zone.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiosqlite
import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.config import HyperSussySettings
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

# HL's ``candleSnapshot`` returns at most this many bars per request.
# We walk backward in chunks of this size during backfill.
_HL_CANDLE_CAP = 5000

# Absolute floor for backfill ``startTime``. HL returns nothing
# older than this for most assets and negative timestamps are
# invalid input; treat this as the earliest point we'll probe.
_EARLIEST_MS = 0

_UPSERT_SQL = """
INSERT OR REPLACE INTO candles
    (coin, interval_str, timestamp_ms, open, high, low, close, volume, num_trades)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_NEWEST_BEFORE_SQL = """
SELECT timestamp_ms, open, high, low, close, volume, num_trades
FROM candles
WHERE coin = ? AND interval_str = ? AND timestamp_ms < ?
ORDER BY timestamp_ms DESC
LIMIT ?
"""

_COUNT_BEFORE_SQL = """
SELECT COUNT(*) FROM candles
WHERE coin = ? AND interval_str = ? AND timestamp_ms < ?
"""

_MAX_TS_SQL = """
SELECT MAX(timestamp_ms) FROM candles
WHERE coin = ? AND interval_str = ?
"""

_MIN_TS_BELOW_SQL = """
SELECT MIN(timestamp_ms) FROM candles
WHERE coin = ? AND interval_str = ? AND timestamp_ms < ?
"""

_MIN_TS_SQL = """
SELECT MIN(timestamp_ms) FROM candles
WHERE coin = ? AND interval_str = ?
"""


class CandleService:
    """Async cursor-paginated candle cache with lazy backfill.

    Args:
        base_url: Hyperliquid API base URL.
        db_path: Path to the SQLite database file.
        rate_limit_weight: Max API weight budget for candle fetches.
        window_seconds: Rate limiter sliding window duration.
        settings: Shared settings instance — consulted each call for
            ``candles_page_size`` and ``candles_max_backfill_chunks``
            so live Config-page edits take effect. ``None`` pins the
            defaults at construction time (used by tests).
        default_page_size: Fallback page size when ``settings`` isn't
            provided. Ignored when ``settings`` is given.
        max_backfill_chunks: Fallback chunk cap when ``settings`` isn't
            provided. Ignored when ``settings`` is given.
    """

    def __init__(
        self,
        base_url: str,
        db_path: str,
        rate_limit_weight: int = 200,
        window_seconds: int = 60,
        *,
        settings: HyperSussySettings | None = None,
        default_page_size: int = 1500,
        max_backfill_chunks: int = 8,
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
        self._settings = settings
        self._fallback_page_size = default_page_size
        self._fallback_max_chunks = max_backfill_chunks
        # Per-(coin, interval) locks so two concurrent requests for the
        # same chart don't both backfill the same range. We keep the
        # dict bounded loosely — locks that haven't been used in a
        # while stay around but cost ~200 bytes each.
        self._fetch_locks: dict[tuple[str, str], asyncio.Lock] = {}

    @property
    def _default_page_size(self) -> int:
        """Read live from settings when wired, else fall back to ctor arg."""
        if self._settings is not None:
            return self._settings.candles_page_size
        return self._fallback_page_size

    @property
    def _max_backfill_chunks(self) -> int:
        """Read live from settings when wired, else fall back to ctor arg."""
        if self._settings is not None:
            return self._settings.candles_max_backfill_chunks
        return self._fallback_max_chunks

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

    @property
    def _conn(self) -> aiosqlite.Connection:
        """Return the active connection or raise.

        Raises:
            RuntimeError: If init() has not been called yet, or if
                close() has already been called.
        """
        if self._db is None:
            msg = "CandleService not initialised. Call init() first."
            raise RuntimeError(msg)
        return self._db

    def _fetch_lock(self, coin: str, interval: str) -> asyncio.Lock:
        """Return the per-pair HL fetch lock, creating it if absent."""
        key = (coin, interval)
        lock = self._fetch_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._fetch_locks[key] = lock
        return lock

    async def get_candle_page(
        self,
        coin: str,
        interval: str,
        before_ms: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Return up to ``limit`` bars strictly before ``before_ms``.

        Bars are returned oldest-first so the frontend can append
        them to the candle series without re-sorting. When
        ``before_ms`` is ``None`` the cursor defaults to "now + 1 ms"
        (i.e. the newest bar). When the on-disk cache holds fewer
        than ``limit`` bars before the cursor, the service walks
        backward through HL in chunks until it has enough (or HL
        stops returning data, whichever is first).

        Args:
            coin: Asset ticker symbol.
            interval: Candle interval string (``1m``, ``5m``, ``15m``,
                ``1h``, ``4h``, ``1d``).
            before_ms: Exclusive upper bound on ``timestamp_ms``.
                ``None`` → newest bars.
            limit: Maximum rows to return. ``None`` uses the
                constructor default.

        Returns:
            List of candle dicts ordered oldest-first.
        """
        interval_ms = _INTERVAL_MS[interval]
        now_ms = int(time.time() * 1000)
        page_size = limit if limit is not None else self._default_page_size
        # ``end_ms`` is exclusive — the oldest bar on the previous
        # page sits exactly at ``before_ms`` and must not repeat.
        end_ms = before_ms if before_ms is not None else now_ms + 1

        async with self._fetch_lock(coin, interval):
            if before_ms is None:
                # Initial load: keep the newest end current before
                # serving. Skipped for pagination (cursor path) where
                # a stale tail doesn't matter and a REST hop would
                # just slow the scroll down.
                await self._maybe_top_up(coin, interval, interval_ms, now_ms, page_size)

            cached = await self._count_before(coin, interval, end_ms)
            if cached < page_size:
                await self._backfill_until_count(
                    coin, interval, interval_ms, end_ms, page_size
                )

        return await self._read_newest_before(coin, interval, end_ms, page_size)

    async def _maybe_top_up(
        self,
        coin: str,
        interval: str,
        interval_ms: int,
        now_ms: int,
        page_size: int,
    ) -> None:
        """Refresh newest bars if the cache is staler than 2 intervals.

        Pulls a short window that extends back to the cache's newest
        bar (or ``page_size`` intervals, if the cache is empty) so
        the first render sees a current tape.
        """
        current_max = await self._query_max_ts(coin, interval)
        if current_max is not None and (now_ms - current_max) <= 2 * interval_ms:
            return
        start_ms = (
            max(_EARLIEST_MS, current_max + interval_ms)
            if current_max is not None
            else max(_EARLIEST_MS, now_ms - page_size * interval_ms)
        )
        try:
            candles = await self._reader.get_candles(
                coin=coin, interval=interval, start_ms=start_ms, end_ms=now_ms
            )
        except (ClientError, ServerError, requests.RequestException, OSError):
            logger.warning(
                "HL candle top-up failed for %s/%s; serving whatever cache holds",
                coin,
                interval,
                exc_info=True,
            )
            return
        await self._upsert_batch(candles)

    async def _backfill_until_count(
        self,
        coin: str,
        interval: str,
        interval_ms: int,
        end_ms: int,
        target_count: int,
    ) -> None:
        """Walk HL backward until cache has ``target_count`` bars before ``end_ms``.

        The "how many bars does the window hold" framing — rather
        than "what's the oldest timestamp" — matters because HL
        doesn't always deliver contiguous bars. A listing pause or
        zero-volume day can leave gaps that time-window coverage
        checks won't close, but the count-based check does.

        Exits on any of:

        * Cached count reaches ``target_count``.
        * HL returned zero bars (asset predates the chunk range).
        * HL returned bars but none older than the current anchor
          (no progress — avoid infinite loop on malformed responses).
        * Safety cap ``_max_backfill_chunks`` hit.
        """
        cached = await self._count_before(coin, interval, end_ms)
        if cached >= target_count:
            return
        anchor = await self._query_min_ts_below(coin, interval, end_ms)
        if anchor is None:
            anchor = end_ms
        for _ in range(self._max_backfill_chunks):
            if cached >= target_count:
                return
            # One chunk = up to HL's per-request cap of bars, measured
            # as interval units back from the anchor.
            chunk_start = max(_EARLIEST_MS, anchor - _HL_CANDLE_CAP * interval_ms)
            try:
                candles = await self._reader.get_candles(
                    coin=coin,
                    interval=interval,
                    start_ms=chunk_start,
                    end_ms=anchor - 1,
                )
            except (ClientError, ServerError, requests.RequestException, OSError):
                logger.warning(
                    "HL candle backfill failed for %s/%s (start=%d, end=%d)",
                    coin,
                    interval,
                    chunk_start,
                    anchor - 1,
                    exc_info=True,
                )
                return
            if not candles:
                # Exchange has no more history; stop cleanly.
                return
            await self._upsert_batch(candles)
            new_min = min(c.timestamp_ms for c in candles)
            if new_min >= anchor:
                # No progress — HL re-served the same range. Bail.
                return
            anchor = new_min
            cached = await self._count_before(coin, interval, end_ms)
        logger.debug(
            "Backfill safety cap hit for %s/%s; returning what we have",
            coin,
            interval,
        )

    async def _upsert_batch(self, candles: list) -> None:  # type: ignore[type-arg]
        """Persist a batch of ``CandleBar`` objects."""
        if not candles:
            return
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
        db = self._conn
        await db.executemany(_UPSERT_SQL, params)
        await db.commit()

    async def _query_max_ts(self, coin: str, interval: str) -> int | None:
        async with self._conn.execute(_MAX_TS_SQL, (coin, interval)) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    async def _query_min_ts_below(
        self, coin: str, interval: str, end_ms: int
    ) -> int | None:
        """Oldest cached bar strictly before ``end_ms``."""
        async with self._conn.execute(
            _MIN_TS_BELOW_SQL, (coin, interval, end_ms)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    async def _count_before(self, coin: str, interval: str, end_ms: int) -> int:
        """Count cached bars with ``timestamp_ms < end_ms``."""
        async with self._conn.execute(
            _COUNT_BEFORE_SQL, (coin, interval, end_ms)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    async def _read_newest_before(
        self,
        coin: str,
        interval: str,
        end_ms: int,
        limit: int,
    ) -> list[dict[str, object]]:
        """Read the newest ``limit`` bars before ``end_ms``, returned oldest-first.

        SQL selects newest-first with ``LIMIT`` so the query plan
        uses the PK's descending seek; the Python reversal runs once
        at the tail and is cheap compared to the alternative of a
        window-bounded ASC scan that materialises every in-range bar.
        """
        async with self._conn.execute(
            _SELECT_NEWEST_BEFORE_SQL, (coin, interval, end_ms, limit)
        ) as cursor:
            rows = list(await cursor.fetchall())
        rows.reverse()
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

    async def earliest_cached_ms(self, coin: str, interval: str) -> int | None:
        """Expose the oldest cached bar for observability / debugging."""
        async with self._conn.execute(_MIN_TS_SQL, (coin, interval)) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None
