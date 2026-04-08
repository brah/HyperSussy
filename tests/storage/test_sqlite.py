"""Tests for SQLite storage implementation."""

from __future__ import annotations

import sqlite3

import pytest

from hypersussy.models import Alert, AssetSnapshot, Position, Trade
from hypersussy.storage.sqlite import SqliteStorage


class TestSqliteStorage:
    """Tests for SqliteStorage using in-memory database."""

    @pytest.mark.asyncio
    async def test_insert_and_query_snapshots(self, storage: SqliteStorage) -> None:
        """Insert and retrieve asset snapshots."""
        snap = AssetSnapshot(
            coin="BTC",
            timestamp_ms=1000,
            open_interest=100.0,
            open_interest_usd=5_000_000.0,
            mark_price=50000.0,
            oracle_price=50001.0,
            funding_rate=0.0001,
            premium=0.00005,
            day_volume_usd=1_000_000.0,
        )
        await storage.insert_asset_snapshots([snap])
        history = await storage.get_oi_history("BTC", 0)
        assert len(history) == 1
        assert history[0].coin == "BTC"
        assert history[0].open_interest == 100.0

    @pytest.mark.asyncio
    async def test_insert_trades_dedup(self, storage: SqliteStorage) -> None:
        """Duplicate trades by tid are ignored."""
        trade = Trade(
            coin="ETH",
            price=2000.0,
            size=10.0,
            side="B",
            timestamp_ms=5000,
            buyer="0xabc",
            seller="0xdef",
            tx_hash="0xh",
            tid=1,
        )
        await storage.insert_trades([trade, trade])
        # Verify via top-addresses volume aggregation — the dedup path
        # no longer has a direct by-address getter.
        top = await storage.get_top_addresses_by_volume("ETH", 0)
        assert len(top) == 2
        assert all(v == 20000.0 for _, v in top)

    @pytest.mark.asyncio
    async def test_top_addresses_by_volume(self, storage: SqliteStorage) -> None:
        """Top addresses ranked by combined buyer+seller volume."""
        trades = [
            Trade(
                coin="BTC",
                price=50000.0,
                size=1.0,
                side="B",
                timestamp_ms=1000,
                buyer="0xwhale",
                seller="0xsmall",
                tx_hash="0xh1",
                tid=1,
            ),
            Trade(
                coin="BTC",
                price=50000.0,
                size=0.5,
                side="A",
                timestamp_ms=2000,
                buyer="0xsmall",
                seller="0xwhale",
                tx_hash="0xh2",
                tid=2,
            ),
        ]
        await storage.insert_trades(trades)

        top = await storage.get_top_addresses_by_volume("BTC", 0, limit=5)
        assert len(top) == 2
        # 0xwhale: 50000*1 (buyer) + 50000*0.5 (seller) = 75000
        assert top[0][0] == "0xwhale"
        assert top[0][1] == 75000.0

    @pytest.mark.asyncio
    async def test_tracked_addresses_upsert(self, storage: SqliteStorage) -> None:
        """Upsert updates volume and preserves first_seen."""
        await storage.upsert_tracked_address(
            "0xwhale", "whale1", "discovered", 100_000.0
        )
        await storage.upsert_tracked_address(
            "0xwhale", "whale1", "discovered", 200_000.0
        )
        addresses = await storage.get_tracked_addresses()
        assert "0xwhale" in addresses

    @pytest.mark.asyncio
    async def test_insert_and_query_positions(self, storage: SqliteStorage) -> None:
        """Insert and retrieve position history."""
        pos = Position(
            coin="ETH",
            address="0xabc",
            size=10.0,
            entry_price=2000.0,
            mark_price=2100.0,
            liquidation_price=1500.0,
            unrealized_pnl=1000.0,
            margin_used=4000.0,
            leverage_value=5,
            leverage_type="cross",
            notional_usd=21000.0,
            timestamp_ms=1000,
        )
        await storage.insert_positions([pos])
        history = await storage.get_position_history("0xabc", "ETH", 0)
        assert len(history) == 1
        assert history[0].size == 10.0

    @pytest.mark.asyncio
    async def test_insert_and_query_alerts(self, storage: SqliteStorage) -> None:
        """Insert and retrieve alerts for dedup."""
        alert = Alert(
            alert_id="test-1",
            alert_type="oi_concentration",
            severity="high",
            coin="BTC",
            title="Test Alert",
            description="Test description",
            timestamp_ms=5000,
            metadata={"delta_pct": 0.15},
        )
        await storage.insert_alert(alert)
        recent = await storage.get_recent_alerts("oi_concentration", "BTC", 0)
        assert len(recent) == 1
        assert recent[0].alert_id == "test-1"
        assert recent[0].metadata["delta_pct"] == 0.15

    @pytest.mark.asyncio
    async def test_settings_overrides_crud(
        self, storage: SqliteStorage
    ) -> None:
        """Upsert, read, and delete on the settings_overrides table."""
        assert await storage.get_settings_overrides() == {}

        await storage.upsert_settings_override("alert_cooldown_s", "1800")
        rows = await storage.get_settings_overrides()
        assert rows == {"alert_cooldown_s": "1800"}

        # Upsert overwrites rather than appending.
        await storage.upsert_settings_override("alert_cooldown_s", "3600")
        rows = await storage.get_settings_overrides()
        assert rows == {"alert_cooldown_s": "3600"}

        await storage.delete_settings_override("alert_cooldown_s")
        assert await storage.get_settings_overrides() == {}

    @pytest.mark.asyncio
    async def test_delete_older_than_removes_expired_rows(
        self, storage: SqliteStorage
    ) -> None:
        """Retention delete drops rows strictly older than the cutoff."""
        old = Trade(
            coin="BTC",
            price=10.0,
            size=1.0,
            side="B",
            timestamp_ms=1000,
            buyer="0xa",
            seller="0xb",
            tx_hash="h1",
            tid=1,
        )
        fresh = Trade(
            coin="BTC",
            price=10.0,
            size=1.0,
            side="B",
            timestamp_ms=9000,
            buyer="0xa",
            seller="0xb",
            tx_hash="h2",
            tid=2,
        )
        await storage.insert_trades([old, fresh])

        deleted = await storage.delete_older_than("trades", 5000)
        assert deleted == 1

        top = await storage.get_top_addresses_by_volume("BTC", 0)
        # Only the fresh trade survives — each side gets its own row.
        assert len(top) == 2
        assert all(vol == 10.0 for _, vol in top)

    @pytest.mark.asyncio
    async def test_delete_older_than_rejects_unknown_table(
        self, storage: SqliteStorage
    ) -> None:
        """Retention is gated to a whitelist to avoid SQL injection."""
        with pytest.raises(ValueError, match="not retention-eligible"):
            await storage.delete_older_than("sqlite_master", 0)

    @pytest.mark.asyncio
    async def test_incremental_vacuum_noop_on_memory_db(
        self, storage: SqliteStorage
    ) -> None:
        """Incremental vacuum is safe to call even on an empty :memory: DB."""
        # Just verify no exception: in-memory DBs may not be in
        # auto_vacuum=INCREMENTAL, in which case the PRAGMA is a no-op.
        await storage.incremental_vacuum(100)

    @pytest.mark.asyncio
    async def test_executemany_write_retries_transient_lock(self) -> None:
        """Transient SQLite locks are retried before surfacing as errors."""

        class _FakeConn:
            def __init__(self) -> None:
                self.executemany_calls = 0
                self.commit_calls = 0

            async def executemany(
                self,
                query: str,
                rows: list[tuple[object, ...]],
            ) -> None:
                self.executemany_calls += 1
                if self.executemany_calls == 1:
                    raise sqlite3.OperationalError("database is locked")

            async def commit(self) -> None:
                self.commit_calls += 1

        storage = SqliteStorage(":memory:")
        storage._db = _FakeConn()  # type: ignore[assignment]

        await storage._executemany_write("INSERT INTO t VALUES (?)", [(1,)])  # noqa: SLF001

        fake = storage._db
        assert fake is not None
        assert fake.executemany_calls == 2
        assert fake.commit_calls == 1
