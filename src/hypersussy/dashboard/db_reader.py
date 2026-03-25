"""Synchronous read-only SQLite queries for the Streamlit dashboard.

Opens a separate sqlite3 connection in WAL read-only mode so Streamlit's
main thread can query history without conflicting with the async writer.
All methods return plain Python dicts; no asyncio required.
"""

from __future__ import annotations

import sqlite3
import time


class DashboardReader:
    """Read-only SQLite interface for dashboard pages.

    Uses a URI connection with mode=ro so no writes are possible on the
    primary connection.  A separate writable connection is lazily created
    for mutation operations (add / remove tracked addresses).

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            isolation_level=None,  # autocommit — never hold implicit read transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._write_conn: sqlite3.Connection | None = None

    def _get_write_conn(self) -> sqlite3.Connection:
        """Lazily open a writable connection for mutation operations.

        Returns:
            A writable sqlite3 connection with busy_timeout set.
        """
        if self._write_conn is None:
            self._write_conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._write_conn.execute("PRAGMA busy_timeout=5000")
        return self._write_conn

    # -- Mutations --

    def delete_tracked_address(self, address: str) -> None:
        """Remove a tracked whale address.

        Args:
            address: The 0x address to remove.
        """
        conn = self._get_write_conn()
        conn.execute("DELETE FROM tracked_addresses WHERE address = ?", (address,))
        conn.commit()

    def insert_tracked_address(self, address: str, label: str) -> None:
        """Manually add a whale address for tracking.

        Args:
            address: The 0x address.
            label: Human-readable label.
        """
        now_ms = int(time.time() * 1000)
        conn = self._get_write_conn()
        conn.execute(
            """INSERT OR IGNORE INTO tracked_addresses
               (address, label, source, first_seen_ms,
                total_volume_usd, last_active_ms, is_manual)
               VALUES (?, ?, 'manual', ?, 0.0, ?, 1)""",
            (address, label, now_ms, now_ms),
        )
        conn.commit()

    # -- Alerts --

    def get_alerts_all(
        self,
        limit: int = 200,
        since_ms: int = 0,
    ) -> list[dict[str, object]]:
        """Fetch recent alerts ordered newest-first.

        Args:
            limit: Maximum number of rows to return.
            since_ms: Only return alerts after this timestamp (ms).

        Returns:
            List of alert dicts.  Includes an ``address`` key extracted
            from metadata via ``json_extract`` at the SQL level.
        """
        cur = self._conn.execute(
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
        return [dict(row) for row in cur.fetchall()]

    # -- Snapshots --

    def get_oi_history(
        self,
        coin: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch open interest snapshots for a coin over the past N hours.

        Args:
            coin: Asset ticker symbol.
            hours: Lookback window in hours.

        Returns:
            List of dicts with keys: timestamp_ms, open_interest_usd,
            mark_price, funding_rate.
        """
        since_ms = int((time.time() - hours * 3600) * 1000)
        cur = self._conn.execute(
            """
            SELECT timestamp_ms, open_interest_usd, mark_price, funding_rate
            FROM asset_snapshots
            WHERE coin = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (coin, since_ms),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_funding_history(
        self,
        coin: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch funding rate history for a coin over the past N hours.

        Args:
            coin: Asset ticker symbol.
            hours: Lookback window in hours.

        Returns:
            List of dicts with keys: timestamp_ms, funding_rate, premium,
            mark_price, oracle_price.
        """
        since_ms = int((time.time() - hours * 3600) * 1000)
        cur = self._conn.execute(
            """
            SELECT timestamp_ms, funding_rate, premium, mark_price, oracle_price
            FROM asset_snapshots
            WHERE coin = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (coin, since_ms),
        )
        return [dict(row) for row in cur.fetchall()]

    # -- Trades --

    def get_top_whales(
        self,
        coin: str,
        hours: int = 1,
    ) -> list[dict[str, object]]:
        """Top addresses by volume (buyer + seller combined) for a coin.

        Args:
            coin: Asset ticker symbol.
            hours: Lookback window in hours.

        Returns:
            List of dicts with keys: address, volume_usd, ordered by
            volume_usd descending.
        """
        since_ms = int((time.time() - hours * 3600) * 1000)
        cur = self._conn.execute(
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
        return [dict(row) for row in cur.fetchall()]

    def get_trades_by_address(
        self,
        address: str,
        hours: int = 24,
    ) -> list[dict[str, object]]:
        """Fetch recent trades involving an address.

        Args:
            address: The 0x address (matched as buyer or seller).
            hours: Lookback window in hours.

        Returns:
            List of trade dicts ordered newest-first, up to 200 rows.
        """
        since_ms = int((time.time() - hours * 3600) * 1000)
        cur = self._conn.execute(
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
        return [dict(row) for row in cur.fetchall()]

    # -- Tracked addresses --

    def get_tracked_addresses(
        self,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """Fetch tracked whale addresses ordered by total volume.

        Args:
            limit: Maximum number of addresses to return.

        Returns:
            List of dicts with keys: address, label, total_volume_usd,
            last_active_ms, source.
        """
        cur = self._conn.execute(
            """
            SELECT address, label, total_volume_usd, last_active_ms, source
            FROM tracked_addresses
            ORDER BY total_volume_usd DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_tracked_address_count(self) -> int:
        """Return the total number of tracked whale addresses.

        Returns:
            Count of rows in tracked_addresses table.
        """
        cur = self._conn.execute("SELECT COUNT(*) FROM tracked_addresses")
        return int(cur.fetchone()[0])

    def get_whale_positions(
        self,
        address: str,
    ) -> list[dict[str, object]]:
        """Latest position per coin for a tracked whale address.

        Args:
            address: The 0x whale address.

        Returns:
            List of dicts with keys: coin, size, notional_usd,
            unrealized_pnl, liquidation_price, mark_price, timestamp_ms.
        """
        cur = self._conn.execute(
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
        return [dict(row) for row in cur.fetchall()]

    # -- Alert aggregations --

    def get_alert_counts_by_type(
        self,
        since_ms: int = 0,
    ) -> dict[str, int]:
        """Count of alerts per engine type since a given timestamp.

        Args:
            since_ms: Only count alerts after this timestamp (ms).

        Returns:
            Mapping of alert_type to count.
        """
        cur = self._conn.execute(
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
        """Fetch alerts associated with a tracked whale address.

        Uses SQLite's json_extract to match alerts whose metadata
        contains the given address.

        Args:
            address: The 0x whale address.
            limit: Maximum alerts to return.

        Returns:
            List of dicts with keys: alert_type, severity, coin, title,
            timestamp_ms; ordered newest-first.
        """
        cur = self._conn.execute(
            """
            SELECT alert_type, severity, coin, title, timestamp_ms
            FROM alerts
            WHERE json_extract(metadata_json, '$.address') = ?
            ORDER BY timestamp_ms DESC
            LIMIT ?
            """,
            (address, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_latest_oi_per_coin(self) -> dict[str, float]:
        """Latest open interest (base units) per coin from asset_snapshots.

        Returns:
            Mapping of coin symbol to most recent open_interest value.
        """
        cur = self._conn.execute(
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
        """Return distinct coin symbols present in asset_snapshots.

        Returns:
            Sorted list of coin symbols.
        """
        cur = self._conn.execute(
            "SELECT DISTINCT coin FROM asset_snapshots ORDER BY coin"
        )
        return [row["coin"] for row in cur.fetchall()]

    def close(self) -> None:
        """Close all database connections."""
        self._conn.close()
        if self._write_conn is not None:
            self._write_conn.close()
