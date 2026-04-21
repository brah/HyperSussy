"""Tests for the alert manager."""

from __future__ import annotations

import pytest

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
from hypersussy.models import Alert
from hypersussy.storage.sqlite import SqliteStorage


class _MockSink:
    """Test sink that records dispatched alerts."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    async def send(self, alert: Alert) -> None:
        """Record the alert.

        Args:
            alert: Alert to record.
        """
        self.alerts.append(alert)


def _make_alert(
    alert_id: str = "test-1",
    coin: str = "BTC",
    ts: int = 5000,
    metadata: dict[str, float | str | list[str]] | None = None,
) -> Alert:
    """Helper to create a test alert.

    Args:
        alert_id: Unique alert ID.
        coin: Asset name.
        ts: Timestamp in milliseconds.

    Returns:
        A test Alert instance.
    """
    return Alert(
        alert_id=alert_id,
        alert_type="oi_concentration",
        severity="high",
        coin=coin,
        title="Test Alert",
        description="Test",
        timestamp_ms=ts,
        metadata=metadata or {},
    )


class TestAlertManager:
    """Tests for AlertManager."""

    @pytest.mark.asyncio
    async def test_dispatches_new_alert(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """New alerts are dispatched to all sinks."""
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)
        result = await manager.process_alert(_make_alert())
        assert result is True
        assert len(sink.alerts) == 1

    @pytest.mark.asyncio
    async def test_deduplicates_same_type_coin(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Duplicate alerts within cooldown are suppressed."""
        settings.alert_cooldown_s = 3600
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)
        await manager.process_alert(_make_alert("a1", ts=5000))
        result = await manager.process_alert(_make_alert("a2", ts=6000))
        assert result is False
        assert len(sink.alerts) == 1

    @pytest.mark.asyncio
    async def test_different_coins_not_deduped(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Alerts for different coins are not deduplicated."""
        settings.alert_cooldown_s = 3600
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)
        await manager.process_alert(_make_alert("a1", coin="BTC", ts=5000))
        result = await manager.process_alert(_make_alert("a2", coin="ETH", ts=6000))
        assert result is True
        assert len(sink.alerts) == 2

    @pytest.mark.asyncio
    async def test_same_coin_different_addresses_not_deduped(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Address-scoped alerts should not suppress different wallets."""
        settings.alert_cooldown_s = 3600
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)
        await manager.process_alert(
            _make_alert("a1", ts=5000, metadata={"address": "0xaaa"})
        )
        result = await manager.process_alert(
            _make_alert("a2", ts=6000, metadata={"address": "0xbbb"})
        )
        assert result is True
        assert len(sink.alerts) == 2

    @pytest.mark.asyncio
    async def test_dedup_uses_in_memory_cache_after_first_dispatch(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """After the first dispatch, dedup must not hit storage again.

        Verifies the in-memory fingerprint cache short-circuits
        before the ``get_recent_alerts`` fallback. Without this, a
        burst of duplicate alerts on the hot path would issue one
        SQLite scan per duplicate.
        """
        settings.alert_cooldown_s = 3600
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)

        # First call seeds the cache via the storage fallback.
        await manager.process_alert(_make_alert("a1", ts=5000))

        # Swap get_recent_alerts for a counter — if the cache is
        # authoritative, this must not be awaited for duplicates.
        calls = 0

        async def _counting(*args: object, **kwargs: object) -> list[Alert]:
            nonlocal calls
            calls += 1
            return []

        storage.get_recent_alerts = _counting  # type: ignore[method-assign]

        for i in range(5):
            await manager.process_alert(_make_alert(f"dup{i}", ts=5000 + i))

        assert calls == 0, "dedup fell through to storage on a cache hit"

    @pytest.mark.asyncio
    async def test_dedup_falls_through_to_storage_on_first_sight(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """On first sight, dedup honours persisted cooldown.

        Pins the safety net: a fingerprint that already had an alert
        dispatched in a *previous* process run must be blocked on the
        very first in-memory check of the new run.
        """
        settings.alert_cooldown_s = 3600
        # Pre-populate storage as if a prior run dispatched an alert.
        previous = _make_alert("prior", ts=5000)
        await storage.insert_alert(previous)

        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)

        # New process, fresh in-memory cache; same fingerprint at t=6000.
        result = await manager.process_alert(_make_alert("new", ts=6000))

        assert result is False, "persisted cooldown must survive a restart"
        assert len(sink.alerts) == 0

    @pytest.mark.asyncio
    async def test_throttle_limits_rate(
        self,
        storage: SqliteStorage,
        settings: HyperSussySettings,
    ) -> None:
        """Global throttle limits dispatches per minute."""
        settings.alert_max_per_minute = 2
        settings.alert_cooldown_s = 0
        sink = _MockSink()
        manager = AlertManager(storage=storage, sinks=[sink], settings=settings)
        await manager.process_alert(_make_alert("a1", coin="BTC", ts=1000))
        await manager.process_alert(_make_alert("a2", coin="ETH", ts=2000))
        result = await manager.process_alert(_make_alert("a3", coin="SOL", ts=3000))
        assert result is False
        assert len(sink.alerts) == 2
