"""Tests for DashboardReader using a workspace-local SQLite database."""

from __future__ import annotations

import importlib.resources
import sqlite3
import time
from pathlib import Path

import pytest

from hypersussy.dashboard.db_reader import DashboardReader


@pytest.fixture
def db_path() -> str:
    """Create a temp SQLite DB with the real schema and seed data."""
    path = Path(f"db_reader_test_{time.time_ns()}.db")
    schema_sql = (
        importlib.resources.files("hypersussy.storage")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(path)
    conn.executescript(schema_sql)

    now_ms = int(time.time() * 1000)
    hour_ms = 3_600_000

    conn.executemany(
        """INSERT INTO asset_snapshots
           (coin, timestamp_ms, open_interest, open_interest_usd,
            mark_price, oracle_price, funding_rate, premium, day_volume_usd)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (
                "BTC",
                now_ms - 2 * hour_ms,
                500,
                25_000_000,
                50_000,
                49_950,
                0.0001,
                0.001,
                1e9,
            ),
            (
                "BTC",
                now_ms - hour_ms,
                510,
                25_500_000,
                50_100,
                50_050,
                0.0002,
                0.001,
                1.1e9,
            ),
            (
                "ETH",
                now_ms - hour_ms,
                1000,
                3_000_000,
                3_000,
                2_990,
                -0.0001,
                -0.001,
                5e8,
            ),
        ],
    )

    conn.executemany(
        """INSERT INTO trades
           (tid, coin, price, size, side, timestamp_ms, buyer, seller)
           VALUES (?,?,?,?,?,?,?,?)""",
        [
            (1, "BTC", 50_000, 0.1, "B", now_ms - 1800_000, "addr1", "addr2"),
            (2, "BTC", 50_100, 0.2, "B", now_ms - 900_000, "addr1", "addr2"),
            (3, "BTC", 50_050, 0.1, "A", now_ms - 600_000, "addr3", "addr1"),
        ],
    )

    conn.executemany(
        """INSERT INTO tracked_addresses
           (address, label, total_volume_usd, last_active_ms, first_seen_ms)
           VALUES (?,?,?,?,?)""",
        [
            ("addr1", "whale-a", 500_000, now_ms, now_ms - 86400_000),
            ("addr2", "whale-b", 200_000, now_ms - hour_ms, now_ms - 86400_000),
        ],
    )

    conn.executemany(
        """INSERT INTO address_positions
           (address, coin, timestamp_ms, size, entry_price, notional_usd,
            unrealized_pnl, mark_price)
           VALUES (?,?,?,?,?,?,?,?)""",
        [
            ("addr1", "BTC", now_ms - hour_ms, 1.0, 49_000, 50_100, 1_100, 50_100),
            ("addr1", "BTC", now_ms, 1.5, 49_000, 75_150, 1_650, 50_100),
        ],
    )

    conn.executemany(
        """INSERT INTO alerts
           (alert_id, alert_type, severity, coin, title, description, timestamp_ms)
           VALUES (?,?,?,?,?,?,?)""",
        [
            (
                "a1",
                "funding_anomaly",
                "high",
                "BTC",
                "Funding spike",
                "...",
                now_ms - 2000,
            ),
            (
                "a2",
                "whale_position",
                "medium",
                "ETH",
                "Whale detected",
                "...",
                now_ms - 1000,
            ),
            (
                "a3",
                "funding_anomaly",
                "low",
                "ETH",
                "Minor anomaly",
                "...",
                now_ms,
            ),
        ],
    )
    conn.commit()
    conn.close()
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture
def reader(db_path: str) -> DashboardReader:
    """DashboardReader pointed at the seeded test DB."""
    r = DashboardReader(db_path)
    yield r  # type: ignore[misc]
    r.close()


def test_get_alerts_all_sorted_desc(reader: DashboardReader) -> None:
    """Alerts are returned newest-first."""
    alerts = reader.get_alerts_all(limit=10)
    timestamps = [a["timestamp_ms"] for a in alerts]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_alerts_all_limit(reader: DashboardReader) -> None:
    """limit parameter is respected."""
    alerts = reader.get_alerts_all(limit=1)
    assert len(alerts) == 1


def test_get_alerts_all_since_ms_filter(reader: DashboardReader) -> None:
    """since_ms excludes older alerts."""
    now_ms = int(time.time() * 1000)
    alerts = reader.get_alerts_all(since_ms=now_ms - 1500)
    assert all(a["timestamp_ms"] >= now_ms - 1500 for a in alerts)


def test_get_oi_history_filters_coin(reader: DashboardReader) -> None:
    """Only rows for the requested coin are returned."""
    rows = reader.get_oi_history("ETH", hours=48)
    assert all(r["open_interest_usd"] == 3_000_000 for r in rows)


def test_get_oi_history_sorted_asc(reader: DashboardReader) -> None:
    """Rows are ordered by timestamp ascending (for charting)."""
    rows = reader.get_oi_history("BTC", hours=48)
    timestamps = [r["timestamp_ms"] for r in rows]
    assert timestamps == sorted(timestamps)


def test_get_top_whales_aggregates_volume(reader: DashboardReader) -> None:
    """Buyer and seller volumes for the same address are summed."""
    rows = reader.get_top_whales("BTC", hours=2)
    addr1_row = next((r for r in rows if r["address"] == "addr1"), None)
    assert addr1_row is not None
    expected = (50_000 * 0.1) + (50_100 * 0.2) + (50_050 * 0.1)
    assert abs(addr1_row["volume_usd"] - expected) < 1.0


def test_get_top_whales_excludes_empty_address(reader: DashboardReader) -> None:
    """Empty address strings are excluded from results."""
    rows = reader.get_top_whales("BTC", hours=2)
    assert all(r["address"] != "" for r in rows)


def test_get_tracked_addresses_limit(reader: DashboardReader) -> None:
    """Limit is respected."""
    rows = reader.get_tracked_addresses(limit=1)
    assert len(rows) == 1


def test_get_tracked_addresses_sorted_by_volume(reader: DashboardReader) -> None:
    """Results are ordered by total_volume_usd descending."""
    rows = reader.get_tracked_addresses(limit=10)
    volumes = [r["total_volume_usd"] for r in rows]
    assert volumes == sorted(volumes, reverse=True)


def test_get_whale_positions_returns_latest(reader: DashboardReader) -> None:
    """Only the most recent position per coin is returned."""
    rows = reader.get_whale_positions("addr1")
    btc_rows = [r for r in rows if r["coin"] == "BTC"]
    assert len(btc_rows) == 1
    assert btc_rows[0]["notional_usd"] == pytest.approx(75_150)


def test_get_alert_counts_by_type(reader: DashboardReader) -> None:
    """Returns correct counts per alert type."""
    counts = reader.get_alert_counts_by_type()
    assert counts["funding_anomaly"] == 2
    assert counts["whale_position"] == 1


def test_read_only_rejects_writes(reader: DashboardReader) -> None:
    """DashboardReader connection must not accept writes."""
    with pytest.raises(sqlite3.OperationalError):
        reader._conn.execute(  # noqa: SLF001
            "INSERT INTO alerts (alert_id, alert_type, severity, coin, "
            "title, description, timestamp_ms) VALUES ('x','x','x','x','x','x',1)"
        )
