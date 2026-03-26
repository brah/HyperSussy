"""Synchronous read-only SQLite queries for the FastAPI dashboard."""

from __future__ import annotations

import sqlite3
import time


class DashboardReader:
    """Read-only SQLite interface for API routes."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row

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
        cur = self._conn.execute(query, params)
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
        cur = self._conn.execute("SELECT COUNT(*) FROM tracked_addresses")
        return int(cur.fetchone()[0])

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

    def get_alert_counts_by_type(
        self,
        since_ms: int = 0,
    ) -> dict[str, int]:
        """Count alerts per engine type since a given timestamp."""
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
        """Return distinct coin symbols present in asset snapshots."""
        cur = self._conn.execute(
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
        """Close the read-only database connection."""
        self._conn.close()
