"""SQLite storage implementation with WAL mode and async access."""

from __future__ import annotations

import importlib.resources
import logging
import time

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


class SqliteStorage:
    """Async SQLite storage backend.

    Args:
        db_path: Path to the SQLite database file.
            Use ":memory:" for in-memory databases (testing).
    """

    def __init__(self, db_path: str = "data/hypersussy.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

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
        await self._db.commit()

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

    # -- Asset snapshots --

    async def insert_asset_snapshots(self, snapshots: list[AssetSnapshot]) -> None:
        """Batch insert asset snapshots.

        Args:
            snapshots: List of asset snapshots to store.
        """
        await self._conn.executemany(
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
        await self._conn.commit()

    async def get_oi_history(self, coin: str, since_ms: int) -> list[AssetSnapshot]:
        """Fetch recent OI history for a coin.

        Args:
            coin: Asset name.
            since_ms: Absolute start timestamp in milliseconds.

        Returns:
            Snapshots ordered by timestamp ascending.
        """
        cutoff = since_ms
        cursor = await self._conn.execute(
            """SELECT coin, timestamp_ms, open_interest,
                      open_interest_usd, mark_price, oracle_price,
                      funding_rate, premium, day_volume_usd, mid_price
               FROM asset_snapshots
               WHERE coin = ? AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (coin, cutoff),
        )
        rows = await cursor.fetchall()
        return [
            AssetSnapshot(
                coin=r[0],
                timestamp_ms=r[1],
                open_interest=r[2],
                open_interest_usd=r[3],
                mark_price=r[4],
                oracle_price=r[5],
                funding_rate=r[6],
                premium=r[7],
                day_volume_usd=r[8],
                mid_price=r[9],
            )
            for r in rows
        ]

    # -- Trades --

    async def insert_trades(self, trades: list[Trade]) -> None:
        """Batch insert trades (ignores duplicates by tid).

        Args:
            trades: List of trades to store.
        """
        await self._conn.executemany(
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
        await self._conn.commit()

    async def get_top_addresses_by_volume(
        self,
        coin: str,
        since_ms: int,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Get top trading addresses by notional volume.

        Combines buyer and seller volume into a single ranking.

        Args:
            coin: Asset name.
            since_ms: Start timestamp.
            limit: Max addresses to return.

        Returns:
            List of (address, total_volume_usd) tuples, descending.
        """
        cursor = await self._conn.execute(
            """SELECT address, SUM(vol) as total_vol FROM (
                 SELECT buyer AS address, SUM(price * size) AS vol
                 FROM trades
                 WHERE coin = ? AND timestamp_ms >= ? AND buyer != ''
                 GROUP BY buyer
                 UNION ALL
                 SELECT seller AS address, SUM(price * size) AS vol
                 FROM trades
                 WHERE coin = ? AND timestamp_ms >= ? AND seller != ''
                 GROUP BY seller
               )
               GROUP BY address
               ORDER BY total_vol DESC
               LIMIT ?""",
            (coin, since_ms, coin, since_ms, limit),
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def get_trades_by_address(self, address: str, since_ms: int) -> list[Trade]:
        """Fetch trades for a specific address since a timestamp.

        Args:
            address: The 0x address (as buyer or seller).
            since_ms: Start timestamp.

        Returns:
            List of trades ordered by timestamp.
        """
        cursor = await self._conn.execute(
            """SELECT tid, coin, price, size, side, timestamp_ms,
                      buyer, seller, tx_hash, exchange
               FROM trades
               WHERE (buyer = ? OR seller = ?)
                 AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (address, address, since_ms),
        )
        rows = await cursor.fetchall()
        return [
            Trade(
                tid=r[0],
                coin=r[1],
                price=r[2],
                size=r[3],
                side=r[4],
                timestamp_ms=r[5],
                buyer=r[6],
                seller=r[7],
                tx_hash=r[8],
                exchange=r[9],
            )
            for r in rows
        ]

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
        await self._conn.execute(
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
        await self._conn.commit()

    async def get_tracked_addresses(self) -> list[str]:
        """Get all tracked whale addresses.

        Returns:
            List of 0x addresses ordered by volume descending.
        """
        cursor = await self._conn.execute(
            """SELECT address FROM tracked_addresses
               ORDER BY total_volume_usd DESC"""
        )
        return [row[0] for row in await cursor.fetchall()]

    async def delete_tracked_address(self, address: str) -> None:
        """Remove a tracked whale address.

        Args:
            address: The 0x address to remove.
        """
        await self._conn.execute(
            "DELETE FROM tracked_addresses WHERE address = ?", (address,)
        )
        await self._conn.commit()

    # -- Positions --

    async def insert_positions(self, positions: list[Position]) -> None:
        """Batch insert position snapshots.

        Args:
            positions: List of position snapshots.
        """
        await self._conn.executemany(
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
        await self._conn.commit()

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
        cursor = await self._conn.execute(
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
        rows = await cursor.fetchall()
        return [
            Position(
                address=r[0],
                coin=r[1],
                timestamp_ms=r[2],
                size=r[3],
                entry_price=r[4],
                notional_usd=r[5],
                unrealized_pnl=r[6],
                leverage_value=r[7],
                leverage_type=r[8],
                liquidation_price=r[9],
                mark_price=r[10],
                margin_used=r[11],
            )
            for r in rows
        ]

    async def get_latest_positions(self, address: str) -> list[Position]:
        """Get the most recent position snapshot per coin for an address.

        Args:
            address: The 0x address.

        Returns:
            Latest position per coin (one entry per coin).
        """
        cursor = await self._conn.execute(
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
        rows = await cursor.fetchall()
        return [
            Position(
                address=r[0],
                coin=r[1],
                timestamp_ms=r[2],
                size=r[3],
                entry_price=r[4],
                notional_usd=r[5],
                unrealized_pnl=r[6],
                leverage_value=r[7],
                leverage_type=r[8],
                liquidation_price=r[9],
                mark_price=r[10],
                margin_used=r[11],
            )
            for r in rows
        ]

    # -- Alerts --

    async def insert_alert(self, alert: Alert) -> None:
        """Store a generated alert.

        Args:
            alert: The alert to persist.
        """
        await self._conn.execute(
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
        await self._conn.commit()

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
        cursor = await self._conn.execute(
            """SELECT alert_id, alert_type, severity, coin, title,
                      description, timestamp_ms, metadata_json,
                      exchange
               FROM alerts
               WHERE alert_type = ? AND coin = ?
                 AND timestamp_ms >= ?
               ORDER BY timestamp_ms ASC""",
            (alert_type, coin, since_ms),
        )
        rows = await cursor.fetchall()
        return [
            Alert(
                alert_id=r[0],
                alert_type=r[1],
                severity=r[2],
                coin=r[3],
                title=r[4],
                description=r[5],
                timestamp_ms=r[6],
                metadata=orjson.loads(r[7]) if r[7] else {},
                exchange=r[8],
            )
            for r in rows
        ]

    # -- Candles --

    async def insert_candles(self, candles: list[CandleBar]) -> None:
        """Batch insert candle data (upsert on conflict).

        Args:
            candles: List of candle bars.
        """
        await self._conn.executemany(
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
        await self._conn.commit()

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
        cursor = await self._conn.execute(
            """SELECT coin, interval_str, timestamp_ms, open, high,
                      low, close, volume, num_trades
               FROM candles
               WHERE coin = ? AND interval_str = ?
                 AND timestamp_ms >= ? AND timestamp_ms <= ?
               ORDER BY timestamp_ms ASC""",
            (coin, interval, start_ms, end_ms),
        )
        rows = await cursor.fetchall()
        return [
            CandleBar(
                coin=r[0],
                interval=r[1],
                timestamp_ms=r[2],
                open=r[3],
                high=r[4],
                low=r[5],
                close=r[6],
                volume=r[7],
                num_trades=r[8],
            )
            for r in rows
        ]
