"""Synchronous read-only SQLite queries for the FastAPI dashboard."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass

_STORAGE_STATS_TTL_S = 60.0


@dataclass(frozen=True, slots=True)
class StorageStats:
    """Aggregate row counts for the SQLite store.

    Args:
        asset_snapshots_rows: Total rows in ``asset_snapshots``.
        trades_rows: Total rows in ``trades``.
        address_positions_rows: Total rows in ``address_positions``.
        alerts_rows: Total rows in ``alerts``.
        candles_rows: Total rows in ``candles``.
        tracked_addresses_rows: Total rows in ``tracked_addresses``.
        distinct_coins: Set of distinct coin symbols ever seen in
            ``asset_snapshots``. Returned as a set rather than a count so
            the caller can intersect it with the current live-coin
            universe — a raw historical count would include delisted
            coins and produce > 100% coverage ratios.
        distinct_addresses_positioned: Distinct addresses in ``address_positions``.
        distinct_addresses_traded: Distinct buyer/seller addresses in ``trades``.
    """

    asset_snapshots_rows: int
    trades_rows: int
    address_positions_rows: int
    alerts_rows: int
    candles_rows: int
    tracked_addresses_rows: int
    distinct_coins: frozenset[str]
    distinct_addresses_positioned: int
    distinct_addresses_traded: int


class DashboardReader:
    """Read-only SQLite interface for API routes.

    A single shared :class:`sqlite3.Connection` would serialise every
    parallel API request through one internal mutex — when the frontend
    fires 7 parallel queries on a coin change, the second through seventh
    would block until the first finishes, multiplying total wall time by
    ~7x. Instead this class hands each FastAPI worker thread its own
    read-only connection via :class:`threading.local`. SQLite's
    ``?mode=ro`` URI natively supports any number of concurrent readers,
    so the OS-level file is shared but the connection state is per-thread.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        # Process-wide cache for the storage stats query: COUNT(*) and
        # COUNT(DISTINCT) over the trades table is the slowest query the
        # reader does, and the answer changes slowly. Bound it to one
        # cold call per minute regardless of caller count.
        self._storage_stats_lock = threading.Lock()
        self._storage_stats_cache: StorageStats | None = None
        self._storage_stats_expires_at: float = 0.0

    def _connect(self) -> sqlite3.Connection:
        """Return the calling thread's read-only connection, opening lazily."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro",
                uri=True,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @staticmethod
    def _hours_to_since_ms(hours: int) -> int:
        """Convert a lookback window in hours to a Unix-ms lower bound."""
        return int((time.time() - hours * 3600) * 1000)

    def _fetch_dicts(
        self,
        query: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        """Execute a query and return rows as plain dicts."""
        cur = self._connect().execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def get_alerts_all(
        self,
        limit: int = 200,
        since_ms: int = 0,
    ) -> list[dict[str, object]]:
        """Fetch recent alerts ordered newest-first."""
        return self._fetch_dicts(
            """
            SELECT alert_id, alert_type, severity, coin,
                   title, description, timestamp_ms, exchange,
                   json_extract(metadata_json, '$.address') AS address
            FROM alerts
            WHERE timestamp_ms >= ?
            ORDER BY timestamp_ms DESC
            LIMIT ?
            """,
            (since_ms, limit),
        )

    def get_oi_history(
        self,
        coin: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch open interest snapshots for a coin over the past N hours."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT timestamp_ms, open_interest_usd, mark_price, funding_rate
            FROM asset_snapshots
            WHERE coin = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (coin, since_ms),
        )

    def get_funding_history(
        self,
        coin: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch funding rate history for a coin over the past N hours."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT timestamp_ms, funding_rate, premium, mark_price, oracle_price
            FROM asset_snapshots
            WHERE coin = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (coin, since_ms),
        )

    def get_top_whales(
        self,
        coin: str,
        hours: int = 1,
    ) -> list[dict[str, object]]:
        """Top addresses by combined buy and sell volume for a coin."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT address, SUM(volume_usd) AS volume_usd
            FROM (
                SELECT buyer AS address, SUM(price * size) AS volume_usd
                FROM trades
                WHERE coin = ? AND timestamp_ms >= ?
                GROUP BY buyer

                UNION ALL

                SELECT seller AS address, SUM(price * size) AS volume_usd
                FROM trades
                WHERE coin = ? AND timestamp_ms >= ?
                GROUP BY seller
            )
            WHERE address != ''
            GROUP BY address
            ORDER BY volume_usd DESC
            LIMIT 20
            """,
            (coin, since_ms, coin, since_ms),
        )

    def get_trades_by_address(
        self,
        address: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch recent trades involving an address."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT tid, coin, price, size, side, timestamp_ms,
                   buyer, seller
            FROM trades
            WHERE (buyer = ? OR seller = ?) AND timestamp_ms >= ?
            ORDER BY timestamp_ms DESC
            LIMIT 200
            """,
            (address, address, since_ms),
        )

    def get_tracked_addresses(
        self,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """Fetch tracked whale addresses ordered by total volume."""
        return self._fetch_dicts(
            """
            SELECT address, label, total_volume_usd, last_active_ms, source
            FROM tracked_addresses
            ORDER BY total_volume_usd DESC
            LIMIT ?
            """,
            (limit,),
        )

    def get_tracked_address_count(self) -> int:
        """Return the total number of tracked whale addresses."""
        cur = self._connect().execute("SELECT COUNT(*) FROM tracked_addresses")
        return int(cur.fetchone()[0])

    def get_storage_stats(self) -> StorageStats:
        """Return per-table row counts and distinct-entity counts.

        Cached in-process for ``_STORAGE_STATS_TTL_S`` seconds because the
        ``COUNT(*)`` over ``trades`` and the ``COUNT(DISTINCT)`` UNION over
        buyer/seller are the slowest queries the reader does, and the
        answers change slowly relative to typical render frequency.

        Returns:
            StorageStats with row counts and distinct-entity totals.
        """
        now = time.monotonic()
        with self._storage_stats_lock:
            if (
                self._storage_stats_cache is not None
                and now < self._storage_stats_expires_at
            ):
                return self._storage_stats_cache

        conn = self._connect()
        rows = {
            name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in (
                "asset_snapshots",
                "trades",
                "address_positions",
                "alerts",
                "candles",
                "tracked_addresses",
            )
        }
        distinct_coins = frozenset(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT coin FROM asset_snapshots"
            ).fetchall()
        )
        distinct_positioned = int(
            conn.execute(
                "SELECT COUNT(DISTINCT address) FROM address_positions"
            ).fetchone()[0]
        )
        distinct_traded = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT addr) FROM (
                    SELECT buyer AS addr FROM trades WHERE buyer != ''
                    UNION
                    SELECT seller AS addr FROM trades WHERE seller != ''
                )
                """
            ).fetchone()[0]
        )

        stats = StorageStats(
            asset_snapshots_rows=rows["asset_snapshots"],
            trades_rows=rows["trades"],
            address_positions_rows=rows["address_positions"],
            alerts_rows=rows["alerts"],
            candles_rows=rows["candles"],
            tracked_addresses_rows=rows["tracked_addresses"],
            distinct_coins=distinct_coins,
            distinct_addresses_positioned=distinct_positioned,
            distinct_addresses_traded=distinct_traded,
        )

        with self._storage_stats_lock:
            self._storage_stats_cache = stats
            self._storage_stats_expires_at = time.monotonic() + _STORAGE_STATS_TTL_S
        return stats

    def get_whale_positions(
        self,
        address: str,
    ) -> list[dict[str, object]]:
        """Latest position per coin for a tracked whale address."""
        return self._fetch_dicts(
            """
            SELECT p.coin, p.size, p.notional_usd, p.unrealized_pnl,
                   p.liquidation_price, p.mark_price, p.timestamp_ms
            FROM address_positions p
            INNER JOIN (
                SELECT coin, MAX(timestamp_ms) AS max_ts
                FROM address_positions
                WHERE address = ?
                GROUP BY coin
            ) latest ON p.coin = latest.coin AND p.timestamp_ms = latest.max_ts
            WHERE p.address = ?
            ORDER BY p.notional_usd DESC
            """,
            (address, address),
        )

    def get_top_coin_positions(
        self,
        coin: str,
        limit: int = 25,
        max_age_ms: int = 3_600_000,
    ) -> list[dict[str, object]]:
        """Latest position for every address that holds a position in coin.

        Returns the most recent snapshot per address, filtered to non-zero
        size and not older than ``max_age_ms``, ordered by absolute
        notional descending.

        Args:
            coin: Asset ticker symbol.
            limit: Maximum rows to return.
            max_age_ms: Exclude snapshots older than this (default 1 hour).
                Pass 0 to disable the staleness filter.

        Returns:
            List of position dicts ordered by |notional_usd| descending.
        """
        staleness_clause = ""
        params: list[object] = [coin]
        if max_age_ms > 0:
            cutoff = int(time.time() * 1000) - max_age_ms
            staleness_clause = "AND timestamp_ms >= ?"
            params.append(cutoff)

        params.extend([coin, limit])
        return self._fetch_dicts(
            f"""
            SELECT p.address, p.coin, p.size, p.entry_price, p.notional_usd,
                   p.unrealized_pnl, p.leverage_value, p.leverage_type,
                   p.liquidation_price, p.mark_price, p.margin_used,
                   p.timestamp_ms
            FROM address_positions p
            INNER JOIN (
                SELECT address, MAX(timestamp_ms) AS max_ts
                FROM address_positions
                WHERE coin = ? {staleness_clause}
                GROUP BY address
            ) latest ON p.address = latest.address
                     AND p.timestamp_ms = latest.max_ts
            WHERE p.coin = ? AND p.size != 0
            ORDER BY ABS(p.notional_usd) DESC
            LIMIT ?
            """,
            tuple(params),
        )

    def get_alert_counts_by_type(
        self,
        since_ms: int = 0,
    ) -> dict[str, int]:
        """Count alerts per engine type since a given timestamp."""
        cur = self._connect().execute(
            """
            SELECT alert_type, COUNT(*) AS cnt
            FROM alerts
            WHERE timestamp_ms >= ?
            GROUP BY alert_type
            """,
            (since_ms,),
        )
        return {row["alert_type"]: row["cnt"] for row in cur.fetchall()}

    def get_alerts_by_address(
        self,
        address: str,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """Fetch alerts associated with a tracked whale address."""
        return self._fetch_dicts(
            """
            SELECT alert_type, severity, coin, title, timestamp_ms
            FROM alerts
            WHERE json_extract(metadata_json, '$.address') = ?
            ORDER BY timestamp_ms DESC
            LIMIT ?
            """,
            (address, limit),
        )

    def get_latest_oi_per_coin(self) -> dict[str, float]:
        """Latest open interest per coin from asset snapshots."""
        cur = self._connect().execute(
            """
            SELECT s.coin, s.open_interest
            FROM asset_snapshots s
            INNER JOIN (
                SELECT coin, MAX(timestamp_ms) AS max_ts
                FROM asset_snapshots
                GROUP BY coin
            ) latest ON s.coin = latest.coin
                     AND s.timestamp_ms = latest.max_ts
            """
        )
        return {row["coin"]: float(row["open_interest"]) for row in cur.fetchall()}

    def get_distinct_coins(self) -> list[str]:
        """Return distinct coin symbols present in asset snapshots."""
        cur = self._connect().execute(
            "SELECT DISTINCT coin FROM asset_snapshots ORDER BY coin"
        )
        return [row["coin"] for row in cur.fetchall()]

    def get_candles(
        self,
        coin: str,
        interval: str,
        hours: int = 48,
    ) -> list[dict[str, object]]:
        """Fetch OHLCV candle rows for a coin and interval."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT timestamp_ms, open, high, low, close, volume, num_trades
            FROM candles
            WHERE coin = ? AND interval_str = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (coin, interval, since_ms),
        )

    def get_top_holders_concentration(
        self,
        coin: str,
        hours: int = 24,
        limit: int = 15,
    ) -> list[dict[str, object]]:
        """Top addresses by combined buy and sell volume for a coin."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT address,
                   SUM(vol) AS volume_usd,
                   SUM(SUM(vol)) OVER () AS total_volume
            FROM (
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
            ORDER BY volume_usd DESC
            LIMIT ?
            """,
            (coin, since_ms, coin, since_ms, limit),
        )

    def get_trade_flow_by_hour(
        self,
        coin: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Buy vs sell volume bucketed by hour for a coin."""
        since_ms = self._hours_to_since_ms(hours)
        return self._fetch_dicts(
            """
            SELECT (timestamp_ms / 3600000) * 3600000 AS bucket,
                   side,
                   SUM(price * size) AS volume_usd
            FROM trades
            WHERE coin = ? AND timestamp_ms >= ?
            GROUP BY bucket, side
            ORDER BY bucket ASC
            """,
            (coin, since_ms),
        )

    def close(self) -> None:
        """Close the calling thread's read-only connection if one is open.

        Per-thread connections in other threads are reclaimed by OS file
        handle cleanup at process exit; we deliberately don't try to close
        them from here because there's no safe way to do so without a
        global registry, and they're harmless until shutdown.
        """
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
