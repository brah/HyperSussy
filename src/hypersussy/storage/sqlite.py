"""SQLite storage implementation with WAL mode and async access."""

from __future__ import annotations

import asyncio
import importlib.resources
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import aiosqlite
import orjson

from hypersussy.models import (
    Alert,
    AssetSnapshot,
    CandleBar,
    Position,
    Trade,
)

logger = logging.getLogger(__name__)

_WRITE_RETRY_DELAYS_S = (0.25, 0.5, 1.0, 2.0)

# Whitelist of tables the retention loop may target. Gate-keeping the
# table name this way keeps delete_older_than safe from SQL injection
# even though its `table` parameter is interpolated into the query.
_RETENTION_TABLES: frozenset[str] = frozenset(
    {"trades", "asset_snapshots", "address_positions"}
)


def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
    """Return True when SQLite reports a lock/busy condition."""
    text = str(exc).lower()
    return "database is locked" in text or "database table is locked" in text


class SqliteStorage:
    """Async SQLite storage backend.

    Args:
        db_path: Path to the SQLite database file.
            Use ":memory:" for in-memory databases (testing).
    """

    def __init__(self, db_path: str = "data/hypersussy.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        # Serialises all write (DML + commit) pairs so that concurrent
        # async coroutines cannot interleave executemany → commit sequences,
        # which would piggyback on each other's implicit BEGIN DEFERRED
        # transaction and produce undefined commit boundaries.
        self._write_lock = asyncio.Lock()

    async def init(self) -> None:
        """Open connection, enable WAL mode, and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        schema_sql = (
            importlib.resources.files("hypersussy.storage")
            .joinpath("schema.sql")
            .read_text(encoding="utf-8")
        )
        await self._db.executescript(schema_sql)
        # Drop legacy trade indexes that served the removed
        # /api/trades/by-address endpoint. On an existing DB they can
        # account for ~2 GB of pure dead weight; the VACUUM below will
        # reclaim their pages.
        await self._db.execute("DROP INDEX IF EXISTS idx_trades_buyer_ts")
        await self._db.execute("DROP INDEX IF EXISTS idx_trades_seller_ts")
        await self._db.commit()
        await self._migrate_auto_vacuum()

    async def _migrate_auto_vacuum(self) -> None:
        """Ensure the database is in auto_vacuum=INCREMENTAL mode.

        Without this, plain ``DELETE`` statements leave empty pages in
        the file and ``PRAGMA incremental_vacuum`` is a no-op, so the
        retention loop can never shrink the SQLite file on disk. The
        switch requires a full ``VACUUM`` which rewrites the whole
        file and temporarily needs roughly 2x free disk space, so it
        only runs on the very first boot after this code lands.
        """
        cursor = await self._conn.execute("PRAGMA auto_vacuum")
        row = await cursor.fetchone()
        mode = int(row[0]) if row else 0
        if mode == 2:  # already incremental
            return
        logger.info(
            "Migrating SQLite to auto_vacuum=INCREMENTAL "
            "(one-off VACUUM; this may take a minute on large DBs)",
        )
        await self._conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
        # VACUUM cannot run inside a transaction and implicitly commits;
        # it must be executed outside the write lock / auto-commit chain.
        await self._conn.execute("VACUUM")
        logger.info("SQLite auto_vacuum migration complete")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        """Get the active connection or raise.

        Returns:
            The active aiosqlite connection.

        Raises:
            RuntimeError: If storage has not been initialized.
        """
        if self._db is None:
            msg = "Storage not initialized. Call init() first."
            raise RuntimeError(msg)
        return self._db

    async def _execute_write(
        self,
        query: str,
        params: Sequence[object] = (),
    ) -> None:
        """Execute a single write statement under the shared write lock."""
        async with self._write_lock:
            await self._run_write_with_retry(
                lambda: self._conn.execute(query, params),
            )
            await self._conn.commit()

    async def _executemany_write(
        self,
        query: str,
        rows: Sequence[Sequence[object]],
    ) -> None:
        """Execute a batch write statement under the shared write lock."""
        async with self._write_lock:
            await self._run_write_with_retry(
                lambda: self._conn.executemany(query, rows),
            )
            await self._conn.commit()

    async def _run_write_with_retry(
        self,
        action: Callable[[], Awaitable[object]],
    ) -> None:
        """Retry locked SQLite writes a few times before surfacing the error."""
        for attempt, delay in enumerate((0.0, *_WRITE_RETRY_DELAYS_S), start=1):
            try:
                await action()
                return
            except sqlite3.OperationalError as exc:
                is_retryable = _is_locked_error(exc)
                is_last = attempt > len(_WRITE_RETRY_DELAYS_S)
                if not is_retryable or is_last:
                    raise
                await asyncio.sleep(delay)

    async def _fetchall(
        self,
        query: str,
        params: Sequence[object] = (),
    ) -> list[Sequence[Any]]:
        """Execute a query and return all rows.

        Rows are typed with element type ``Any`` because SQLite columns are
        dynamically typed: each cell may be int, float, str, bytes, or
        None. Callers coerce to the expected scalar type.
        """
        cursor = await self._conn.execute(query, params)
        return list(await cursor.fetchall())

    async def _fetch_scalar(
        self,
        query: str,
        params: Sequence[object] = (),
        *,
        default: float = 0.0,
    ) -> float:
        """Execute a scalar query and return the first value."""
        cursor = await self._conn.execute(query, params)
        row: Sequence[Any] | None = await cursor.fetchone()
        return float(row[0]) if row else default

    @staticmethod
    def _asset_snapshot_from_row(row: Sequence[Any]) -> AssetSnapshot:
        """Hydrate an ``AssetSnapshot`` from a SQLite row tuple."""
        return AssetSnapshot(
            coin=str(row[0]),
            timestamp_ms=int(row[1]),
            open_interest=float(row[2]),
            open_interest_usd=float(row[3]),
            mark_price=float(row[4]),
            oracle_price=float(row[5]),
            funding_rate=float(row[6]),
            premium=float(row[7]),
            day_volume_usd=float(row[8]),
            mid_price=float(row[9]) if row[9] is not None else None,
        )

    @staticmethod
    def _position_from_row(row: Sequence[Any]) -> Position:
        """Hydrate a ``Position`` from a SQLite row tuple."""
        return Position(
            address=str(row[0]),
            coin=str(row[1]),
            timestamp_ms=int(row[2]),
            size=float(row[3]),
            entry_price=float(row[4]),
            notional_usd=float(row[5]),
            unrealized_pnl=float(row[6]),
            leverage_value=int(row[7]),
            leverage_type=str(row[8]),
            liquidation_price=float(row[9]) if row[9] is not None else None,
            mark_price=float(row[10]),
            margin_used=float(row[11]),
        )

    @staticmethod
    def _alert_from_row(row: Sequence[Any]) -> Alert:
        """Hydrate an ``Alert`` from a SQLite row tuple."""
        return Alert(
            alert_id=str(row[0]),
            alert_type=str(row[1]),
            severity=str(row[2]),
            coin=str(row[3]),
            title=str(row[4]),
            description=str(row[5]),
            timestamp_ms=int(row[6]),
            metadata=orjson.loads(row[7]) if row[7] else {},
            exchange=str(row[8]),
        )

    @staticmethod
    def _candle_from_row(row: Sequence[Any]) -> CandleBar:
        """Hydrate a ``CandleBar`` from a SQLite row tuple."""
        return CandleBar(
            coin=str(row[0]),
            interval=str(row[1]),
            timestamp_ms=int(row[2]),
            open=float(row[3]),
            high=float(row[4]),
            low=float(row[5]),
            close=float(row[6]),
            volume=float(row[7]),
            num_trades=int(row[8]),
        )

    # -- Asset snapshots --

    async def insert_asset_snapshots(self, snapshots: list[AssetSnapshot]) -> None:
        """Batch insert asset snapshots.

        Args:
            snapshots: List of asset snapshots to store.
        """
        await self._executemany_write(
            """INSERT OR IGNORE INTO asset_snapshots
               (coin, timestamp_ms, open_interest, open_interest_usd,
                mark_price, oracle_price, funding_rate, premium,
                day_volume_usd, mid_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    s.coin,
                    s.timestamp_ms,
                    s.open_interest,
                    s.open_interest_usd,
                    s.mark_price,
                    s.oracle_price,
                    s.funding_rate,
                    s.premium,
                    s.day_volume_usd,
                    s.mid_price,
                )
                for s in snapshots
            ],
        )

    async def get_oi_history(self, coin: str, since_ms: int) -> list[AssetSnapshot]:
        """Fetch recent OI history for a coin.

        Args:
            coin: Asset name.
            since_ms: Absolute start timestamp in milliseconds.

        Returns:
            Snapshots ordered by timestamp ascending.
        """
        cutoff = since_ms
        rows = await self._fetchall(
            """SELECT coin, timestamp_ms, open_interest,
                      open_interest_usd, mark_price, oracle_price,
                      funding_rate, premium, day_volume_usd, mid_price
               FROM asset_snapshots
               WHERE coin = ? AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (coin, cutoff),
        )
        return [self._asset_snapshot_from_row(row) for row in rows]

    # -- Trades --

    async def insert_trades(self, trades: list[Trade]) -> None:
        """Batch insert trades (ignores duplicates by tid).

        Args:
            trades: List of trades to store.
        """
        await self._executemany_write(
            """INSERT OR IGNORE INTO trades
               (tid, coin, price, size, side, timestamp_ms,
                buyer, seller, tx_hash, exchange)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    t.tid,
                    t.coin,
                    t.price,
                    t.size,
                    t.side,
                    t.timestamp_ms,
                    t.buyer,
                    t.seller,
                    t.tx_hash,
                    t.exchange,
                )
                for t in trades
            ],
        )

    async def get_top_addresses_and_total_volume(
        self,
        coin: str,
        since_ms: int,
        limit: int = 10,
    ) -> tuple[list[tuple[str, float]], float]:
        """Get top addresses by volume and total volume in one query.

        Uses a window function to compute the grand total alongside
        per-address aggregation, eliminating a separate query.

        Args:
            coin: Asset name.
            since_ms: Start timestamp.
            limit: Max addresses to return.

        Returns:
            Tuple of (top_addresses, total_volume_usd).
        """
        rows = list(
            await self._fetchall(
                """SELECT address, addr_vol, total_vol FROM (
                 SELECT address, SUM(vol) AS addr_vol,
                        SUM(SUM(vol)) OVER () AS total_vol
                 FROM (
                     SELECT buyer AS address,
                            SUM(price * size) AS vol
                     FROM trades
                     WHERE coin = ? AND timestamp_ms >= ?
                       AND buyer != ''
                     GROUP BY buyer
                     UNION ALL
                     SELECT seller AS address,
                            SUM(price * size) AS vol
                     FROM trades
                     WHERE coin = ? AND timestamp_ms >= ?
                       AND seller != ''
                     GROUP BY seller
                 )
                 GROUP BY address
                 ORDER BY addr_vol DESC
                 LIMIT ?
               )""",
                (coin, since_ms, coin, since_ms, limit),
            )
        )
        if not rows:
            return [], 0.0
        top = [(row[0], row[1]) for row in rows]
        total = float(rows[0][2])
        return top, total

    # -- Tracked addresses --

    async def upsert_tracked_address(
        self,
        address: str,
        label: str,
        source: str,
        volume_usd: float,
    ) -> None:
        """Insert or update a tracked whale address.

        Args:
            address: The 0x address.
            label: Human-readable label.
            source: Discovery source (e.g. "discovered").
            volume_usd: Cumulative volume.
        """
        now_ms = int(time.time() * 1000)
        await self._execute_write(
            """INSERT INTO tracked_addresses
               (address, label, source, first_seen_ms,
                total_volume_usd, last_active_ms)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(address) DO UPDATE SET
                 total_volume_usd = MAX(
                     tracked_addresses.total_volume_usd,
                     excluded.total_volume_usd
                 ),
                 last_active_ms = excluded.last_active_ms""",
            (address, label, source, now_ms, volume_usd, now_ms),
        )

    async def get_tracked_addresses(self) -> list[str]:
        """Get all tracked whale addresses.

        Returns:
            List of 0x addresses ordered by volume descending.
        """
        rows = await self._fetchall(
            """SELECT address FROM tracked_addresses
               ORDER BY total_volume_usd DESC"""
        )
        return [row[0] for row in rows]

    async def delete_tracked_address(self, address: str) -> None:
        """Remove a tracked whale address.

        Args:
            address: The 0x address to remove.
        """
        await self._execute_write(
            "DELETE FROM tracked_addresses WHERE address = ?", (address,)
        )

    # -- Positions --

    async def insert_positions(self, positions: list[Position]) -> None:
        """Batch insert position snapshots.

        Args:
            positions: List of position snapshots.
        """
        await self._executemany_write(
            """INSERT OR IGNORE INTO address_positions
               (address, coin, timestamp_ms, size, entry_price,
                notional_usd, unrealized_pnl, leverage_value,
                leverage_type, liquidation_price, mark_price,
                margin_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    p.address,
                    p.coin,
                    p.timestamp_ms,
                    p.size,
                    p.entry_price,
                    p.notional_usd,
                    p.unrealized_pnl,
                    p.leverage_value,
                    p.leverage_type,
                    p.liquidation_price,
                    p.mark_price,
                    p.margin_used,
                )
                for p in positions
            ],
        )

    async def get_position_history(
        self, address: str, coin: str, since_ms: int
    ) -> list[Position]:
        """Fetch position history for an address on a coin.

        Args:
            address: The 0x address.
            coin: Asset name.
            since_ms: Absolute start timestamp in milliseconds.

        Returns:
            Positions ordered by timestamp ascending.
        """
        cutoff = since_ms
        rows = await self._fetchall(
            """SELECT address, coin, timestamp_ms, size, entry_price,
                      notional_usd, unrealized_pnl, leverage_value,
                      leverage_type, liquidation_price, mark_price,
                      margin_used
               FROM address_positions
                WHERE address = ? AND coin = ?
                  AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (address, coin, cutoff),
        )
        return [self._position_from_row(row) for row in rows]

    async def get_latest_positions(self, address: str) -> list[Position]:
        """Get the most recent position snapshot per coin for an address.

        Args:
            address: The 0x address.

        Returns:
            Latest position per coin (one entry per coin).
        """
        rows = await self._fetchall(
            """SELECT ap.address, ap.coin, ap.timestamp_ms, ap.size,
                      ap.entry_price, ap.notional_usd, ap.unrealized_pnl,
                      ap.leverage_value, ap.leverage_type,
                      ap.liquidation_price, ap.mark_price, ap.margin_used
               FROM address_positions ap
               INNER JOIN (
                   SELECT address, coin, MAX(timestamp_ms) AS max_ts
                   FROM address_positions
                   WHERE address = ?
                   GROUP BY address, coin
               ) latest
               ON ap.address = latest.address
                  AND ap.coin = latest.coin
                  AND ap.timestamp_ms = latest.max_ts""",
            (address,),
        )
        return [self._position_from_row(row) for row in rows]

    async def get_latest_positions_batch(
        self, addresses: list[str]
    ) -> dict[str, list[Position]]:
        """Batched fetch of latest positions for many addresses.

        Issues a single query with ``address IN (?, ?, ...)`` instead
        of N round-trips through the per-thread cursor. Used by the
        liquidation-risk engine which iterates over every tracked
        whale on each tick.

        Args:
            addresses: 0x addresses to fetch.

        Returns:
            Mapping of address -> list of Position. Addresses with no
            positions are absent from the dict.
        """
        if not addresses:
            return {}
        # Deduplicate so the IN-list and the placeholders match the
        # caller's intent rather than the caller's accidental dupes.
        unique = list(dict.fromkeys(addresses))
        placeholders = ",".join("?" * len(unique))
        rows = await self._fetchall(
            f"""SELECT ap.address, ap.coin, ap.timestamp_ms, ap.size,
                      ap.entry_price, ap.notional_usd, ap.unrealized_pnl,
                      ap.leverage_value, ap.leverage_type,
                      ap.liquidation_price, ap.mark_price, ap.margin_used
               FROM address_positions ap
               INNER JOIN (
                   SELECT address, coin, MAX(timestamp_ms) AS max_ts
                   FROM address_positions
                   WHERE address IN ({placeholders})
                   GROUP BY address, coin
               ) latest
               ON ap.address = latest.address
                  AND ap.coin = latest.coin
                  AND ap.timestamp_ms = latest.max_ts""",  # noqa: S608
            tuple(unique),
        )
        result: dict[str, list[Position]] = {}
        for row in rows:
            position = self._position_from_row(row)
            result.setdefault(position.address, []).append(position)
        return result

    # -- Alerts --

    async def insert_alert(self, alert: Alert) -> None:
        """Store a generated alert.

        Args:
            alert: The alert to persist.
        """
        await self._execute_write(
            """INSERT OR IGNORE INTO alerts
               (alert_id, alert_type, severity, coin, title,
                description, timestamp_ms, metadata_json, exchange)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.alert_id,
                alert.alert_type,
                alert.severity,
                alert.coin,
                alert.title,
                alert.description,
                alert.timestamp_ms,
                orjson.dumps(alert.metadata),
                alert.exchange,
            ),
        )

    async def get_recent_alerts(
        self,
        alert_type: str,
        coin: str,
        since_ms: int,
    ) -> list[Alert]:
        """Fetch recent alerts for deduplication checks.

        Args:
            alert_type: Engine alert type string.
            coin: Asset name.
            since_ms: Start timestamp.

        Returns:
            Matching alerts ordered by timestamp.
        """
        rows = await self._fetchall(
            """SELECT alert_id, alert_type, severity, coin, title,
                      description, timestamp_ms, metadata_json,
                      exchange
               FROM alerts
                WHERE alert_type = ? AND coin = ?
                  AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (alert_type, coin, since_ms),
        )
        return [self._alert_from_row(row) for row in rows]

    # -- Candles --

    async def insert_candles(self, candles: list[CandleBar]) -> None:
        """Batch insert candle data (upsert on conflict).

        Args:
            candles: List of candle bars.
        """
        await self._executemany_write(
            """INSERT OR REPLACE INTO candles
               (coin, interval_str, timestamp_ms, open, high, low,
                close, volume, num_trades)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
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
            ],
        )

    async def get_candles(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[CandleBar]:
        """Fetch cached candle data.

        Args:
            coin: Asset name.
            interval: Candle interval string.
            start_ms: Start timestamp.
            end_ms: End timestamp.

        Returns:
            Candle bars ordered by timestamp.
        """
        rows = await self._fetchall(
            """SELECT coin, interval_str, timestamp_ms, open, high,
                      low, close, volume, num_trades
               FROM candles
               WHERE coin = ? AND interval_str = ?
                AND timestamp_ms >= ? AND timestamp_ms <= ?
               ORDER BY timestamp_ms ASC""",
            (coin, interval, start_ms, end_ms),
        )
        return [self._candle_from_row(row) for row in rows]

    # -- Retention --

    async def delete_older_than(self, table: str, cutoff_ms: int) -> int:
        """Delete rows older than ``cutoff_ms`` from a retention-eligible table.

        Both the DELETE and its commit go through the same retry helper
        the regular write path uses, so a transient ``database is locked``
        from a concurrent writer does not sink an entire retention tick.

        Args:
            table: Must be a member of :data:`_RETENTION_TABLES`.
                Anything else raises ``ValueError`` — this keeps the
                interpolated table name safe from injection.
            cutoff_ms: Rows with ``timestamp_ms`` strictly less than
                this are deleted.

        Returns:
            Number of rows deleted.

        Raises:
            ValueError: If ``table`` is not whitelisted for retention.
        """
        if table not in _RETENTION_TABLES:
            msg = f"table {table!r} is not retention-eligible"
            raise ValueError(msg)

        deleted = 0

        async def _do_delete() -> None:
            nonlocal deleted
            cursor = await self._conn.execute(
                f"DELETE FROM {table} WHERE timestamp_ms < ?",  # noqa: S608
                (cutoff_ms,),
            )
            # DELETE is idempotent under retry: the WHERE clause filters
            # by absolute cutoff, so re-executing after a transient lock
            # just matches zero additional rows.
            deleted = int(cursor.rowcount or 0)

        async with self._write_lock:
            await self._run_write_with_retry(_do_delete)
            await self._conn.commit()
        return deleted

    async def incremental_vacuum(self, pages: int = 2000) -> None:
        """Return freelist pages to the OS.

        No-op unless the database was opened with
        ``auto_vacuum = INCREMENTAL`` (set by :meth:`_migrate_auto_vacuum`).
        Runs through the same retry helper as regular writes so it
        survives transient locks.

        Args:
            pages: Maximum number of freelist pages to release in this
                call. Bounded to avoid long stalls; run repeatedly if
                you need to reclaim more in one sweep.
        """
        pragma = f"PRAGMA incremental_vacuum({int(pages)})"
        async with self._write_lock:
            await self._run_write_with_retry(
                lambda: self._conn.execute(pragma),
            )
            await self._conn.commit()

    # -- Settings overrides --

    async def get_settings_overrides(self) -> dict[str, str]:
        """Return all persisted config overrides as key → JSON value."""
        rows = await self._fetchall(
            "SELECT key, value FROM settings_overrides",
        )
        return {str(row[0]): str(row[1]) for row in rows}

    async def upsert_settings_override(self, key: str, value: str) -> None:
        """Persist a single config override.

        Args:
            key: Setting field name.
            value: JSON-encoded value string.
        """
        now_ms = int(time.time() * 1000)
        await self._execute_write(
            """INSERT INTO settings_overrides (key, value, updated_ms)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_ms = excluded.updated_ms""",
            (key, value, now_ms),
        )

    async def delete_settings_override(self, key: str) -> None:
        """Remove a single persisted config override.

        Args:
            key: Setting field name.
        """
        await self._execute_write(
            "DELETE FROM settings_overrides WHERE key = ?",
            (key,),
        )
