"""Integration tests for the FastAPI REST routes.

Tests wire up a real in-memory SQLite database and a real SharedState so
every route is exercised end-to-end without mocking the production code paths.
The BackgroundRunner is NOT started; only the reader/actions/state are
injected so no network activity occurs.
"""

from __future__ import annotations

import importlib.resources
import os
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hypersussy.api.schemas import (
    AlertItem,
    AlertSummaryItem,
    CandleItem,
    FundingSnapshotItem,
    HealthResponse,
    OISnapshotItem,
    PositionItem,
    TopHolderItem,
    TopWhaleItem,
    TrackedAddressItem,
    TradeFlowItem,
    TradeItem,
    WhaleCountResponse,
)
from hypersussy.api.routes import alerts, candles, health, snapshots, trades, whales
from hypersussy.app.actions import DashboardActions
from hypersussy.app.db_reader import DashboardReader
from hypersussy.app.state import SharedState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> tuple[sqlite3.Connection, str]:
    """Create an in-memory database with the full schema, returning (conn, path)."""
    import tempfile

    # Use a named temp file so DashboardReader (mode=ro) can open it
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path, isolation_level=None)
    schema_sql = (
        importlib.resources.files("hypersussy.storage")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    conn.executescript(schema_sql)
    return conn, path


def _seed_db(conn: sqlite3.Connection) -> None:
    """Insert minimal fixture rows for all route tests."""
    now_ms = int(time.time() * 1000)
    conn.executemany(
        "INSERT INTO asset_snapshots "
        "(coin, timestamp_ms, open_interest, open_interest_usd, mark_price, "
        "oracle_price, funding_rate, premium, day_volume_usd) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            # coin, ts, oi, oi_usd, mark, oracle, funding, premium, vol
            ("BTC", now_ms - 3600_000, 100.0, 5e6, 50000.0, 49900.0, 0.0001, 0.001, 1e6),  # noqa: E501
            ("BTC", now_ms, 110.0, 5.5e6, 50100.0, 50000.0, 0.0002, 0.002, 1.2e6),
            ("ETH", now_ms, 500.0, 1.5e6, 3000.0, 2990.0, -0.0001, -0.001, 5e5),
        ],
    )
    conn.execute(
        "INSERT INTO alerts (alert_id, alert_type, severity, coin, title, description, "
        "timestamp_ms, metadata_json) VALUES (?,?,?,?,?,?,?,?)",
        (
            "alert-1",
            "oi_concentration",
            "high",
            "BTC",
            "High OI concentration",
            "Top 5 wallets hold 80% of OI",
            now_ms,
            '{"address": "0xdeadbeef12345678901234567890123456789012"}',
        ),
    )
    whale = "0xabc1234567890123456789012345678901234567"
    conn.execute(
        "INSERT INTO trades "
        "(tid, coin, price, size, side, timestamp_ms, buyer, seller) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (1, "BTC", 50000.0, 0.5, "B", now_ms, whale, ""),
    )
    conn.execute(
        "INSERT INTO tracked_addresses "
        "(address, label, source, first_seen_ms, total_volume_usd, "
        "last_active_ms, is_manual) VALUES (?,?,?,?,?,?,?)",
        (whale, "Whale A", "auto", now_ms, 500_000.0, now_ms, 0),
    )
    conn.execute(
        "INSERT INTO address_positions "
        "(address, coin, size, entry_price, notional_usd,"
        " unrealized_pnl, leverage_value, leverage_type,"
        " liquidation_price, mark_price, margin_used,"
        " timestamp_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            whale, "BTC", 1.0, 49000.0, 50000.0, 500.0,
            5, "cross", 40000.0, 50000.0, 10000.0, now_ms,
        ),
    )
    conn.execute(
        "INSERT INTO candles "
        "(coin, interval_str, timestamp_ms, open, high, low, close, "
        "volume, num_trades) VALUES (?,?,?,?,?,?,?,?,?)",
        ("BTC", "1h", now_ms - 3600_000, 49800.0, 50200.0, 49700.0, 50100.0, 1.5, 42),
    )


# ---------------------------------------------------------------------------
# Fixture: TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: pytest.TempPathFactory) -> TestClient:  # type: ignore[type-arg]
    """Return a TestClient wired to in-memory DB and real SharedState."""
    conn, db_path = _make_db()
    _seed_db(conn)

    reader = DashboardReader(db_path=db_path)
    actions = DashboardActions(db_path=db_path)
    state = SharedState()
    candle_rows = [
        {
            "timestamp_ms": int(time.time() * 1000) - 3600_000,
            "open": 49800.0,
            "high": 50200.0,
            "low": 49700.0,
            "close": 50100.0,
            "volume": 1.5,
            "num_trades": 42,
        }
    ]
    candle_service = MagicMock()
    candle_service.get_candles = AsyncMock(return_value=candle_rows)

    test_app = FastAPI()
    test_app.include_router(health.router, prefix="/api")
    test_app.include_router(snapshots.router, prefix="/api")
    test_app.include_router(alerts.router, prefix="/api")
    test_app.include_router(trades.router, prefix="/api")
    test_app.include_router(whales.router, prefix="/api")
    test_app.include_router(candles.router, prefix="/api")
    test_app.state.reader = reader
    test_app.state.actions = actions
    test_app.state.shared = state
    test_app.state.candle_service = candle_service

    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c

    conn.close()
    reader.close()
    actions.close()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_schema(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = HealthResponse.model_validate(res.json())
    assert isinstance(body.is_running, bool)
    assert isinstance(body.snapshot_count, int)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def test_get_coins(client: TestClient) -> None:
    res = client.get("/api/snapshots/coins")
    assert res.status_code == 200
    coins = res.json()
    assert "BTC" in coins
    assert "ETH" in coins


def test_get_oi_history(client: TestClient) -> None:
    res = client.get("/api/snapshots/oi/BTC?hours=2")
    assert res.status_code == 200
    items = [OISnapshotItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1
    assert all(i.open_interest_usd > 0 for i in items)


def test_get_funding_history(client: TestClient) -> None:
    res = client.get("/api/snapshots/funding/BTC?hours=2")
    assert res.status_code == 200
    items = [FundingSnapshotItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1


def test_get_latest_oi(client: TestClient) -> None:
    res = client.get("/api/snapshots/latest-oi")
    assert res.status_code == 200
    data = res.json()
    assert "BTC" in data
    assert isinstance(data["BTC"], float)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def test_get_alerts(client: TestClient) -> None:
    res = client.get("/api/alerts?limit=10")
    assert res.status_code == 200
    items = [AlertItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1
    assert items[0].alert_id == "alert-1"


def test_get_alert_counts(client: TestClient) -> None:
    res = client.get("/api/alerts/counts")
    assert res.status_code == 200
    data: dict[str, int] = res.json()
    assert "oi_concentration" in data


def test_get_alerts_by_address_valid(client: TestClient) -> None:
    addr = "0xdeadbeef12345678901234567890123456789012"
    res = client.get(f"/api/alerts/by-address/{addr}?limit=5")
    assert res.status_code == 200
    items = [AlertSummaryItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1


def test_get_alerts_by_address_invalid(client: TestClient) -> None:
    res = client.get("/api/alerts/by-address/not-a-valid-address")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def test_get_top_whales(client: TestClient) -> None:
    res = client.get("/api/trades/top-whales/BTC?hours=2")
    assert res.status_code == 200
    items = [TopWhaleItem.model_validate(r) for r in res.json()]
    assert any(i.address == "0xabc1234567890123456789012345678901234567" for i in items)


def test_get_trades_by_address(client: TestClient) -> None:
    addr = "0xabc1234567890123456789012345678901234567"
    res = client.get(f"/api/trades/by-address/{addr}?hours=2")
    assert res.status_code == 200
    items = [TradeItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1
    assert items[0].coin == "BTC"


def test_get_top_holders(client: TestClient) -> None:
    res = client.get("/api/trades/top-holders/BTC?hours=2&limit=5")
    assert res.status_code == 200
    items = [TopHolderItem.model_validate(r) for r in res.json()]
    assert all(i.volume_usd > 0 for i in items)


def test_get_trade_flow(client: TestClient) -> None:
    res = client.get("/api/trades/flow/BTC?hours=2")
    assert res.status_code == 200
    items = [TradeFlowItem.model_validate(r) for r in res.json()]
    assert all(i.side in ("B", "A") for i in items)


def test_trades_by_address_invalid(client: TestClient) -> None:
    res = client.get("/api/trades/by-address/bad")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Candles
# ---------------------------------------------------------------------------


def test_get_candles(client: TestClient) -> None:
    res = client.get("/api/candles/BTC?interval=1h&hours=2")
    assert res.status_code == 200
    items = [CandleItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1
    assert items[0].open == pytest.approx(49800.0)


def test_get_candles_invalid_interval(client: TestClient) -> None:
    res = client.get("/api/candles/BTC?interval=99x")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Whales
# ---------------------------------------------------------------------------


def test_get_whales(client: TestClient) -> None:
    res = client.get("/api/whales?limit=10")
    assert res.status_code == 200
    items = [TrackedAddressItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1


def test_get_whale_count(client: TestClient) -> None:
    res = client.get("/api/whales/count")
    assert res.status_code == 200
    body = WhaleCountResponse.model_validate(res.json())
    assert body.count >= 1


def test_get_whale_positions(client: TestClient) -> None:
    addr = "0xabc1234567890123456789012345678901234567"
    res = client.get(f"/api/whales/positions/{addr}")
    assert res.status_code == 200
    items = [PositionItem.model_validate(r) for r in res.json()]
    assert len(items) >= 1
    assert items[0].coin == "BTC"


def test_post_whale(client: TestClient) -> None:
    addr = "0x1111111111111111111111111111111111111111"
    res = client.post("/api/whales", json={"address": addr, "label": "Test"})
    assert res.status_code == 201
    assert res.json()["address"] == addr


def test_post_whale_invalid_address(client: TestClient) -> None:
    res = client.post("/api/whales", json={"address": "bad", "label": ""})
    assert res.status_code == 422


def test_delete_whale(client: TestClient) -> None:
    addr = "0x2222222222222222222222222222222222222222"
    # Add first
    client.post("/api/whales", json={"address": addr, "label": ""})
    # Then delete
    res = client.delete(f"/api/whales/{addr}")
    assert res.status_code == 204


def test_delete_whale_invalid_address(client: TestClient) -> None:
    res = client.delete("/api/whales/not-an-address")
    assert res.status_code == 422
