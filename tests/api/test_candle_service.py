"""Tests for the cursor-paginated candle service."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.api.candle_service import CandleService
from hypersussy.models import CandleBar
from hypersussy.storage.sqlite import SqliteStorage


async def _make_service(tmp_path: Path) -> CandleService:
    """Build a CandleService pointing at a fresh SQLite file.

    Schema initialisation piggybacks on :class:`SqliteStorage` rather
    than duplicating ``executescript(schema.sql)`` here — that's the
    same path the API lifespan uses in production.
    """
    db_path = tmp_path / "candles.db"
    bootstrap = SqliteStorage(db_path=str(db_path))
    await bootstrap.init()
    await bootstrap.close()

    service = CandleService(
        base_url="https://example.invalid",
        db_path=str(db_path),
        default_page_size=500,
        max_backfill_chunks=3,
    )
    await service.init()
    return service


def _bar(
    coin: str, interval: str, ts_ms: int, close: float = 100.0
) -> CandleBar:
    return CandleBar(
        coin=coin,
        interval=interval,
        timestamp_ms=ts_ms,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        num_trades=1,
    )


class TestGetCandlePage:
    @pytest.mark.asyncio
    async def test_serves_cached_page_without_hitting_api(
        self,
        tmp_path: Path,
    ) -> None:
        """When the DB already covers the requested window, no HL call."""
        service = await _make_service(tmp_path)
        try:
            now_ms = int(time.time() * 1000)
            interval_ms = 3_600_000
            # Seed 10 hourly bars ending at now and keep the newest one
            # well within the 2-interval freshness window so ``_maybe_top_up``
            # short-circuits and the reader should never be called.
            bars = [_bar("BTC", "1h", now_ms - i * interval_ms) for i in range(10)]
            await service._upsert_batch(bars)  # noqa: SLF001

            service._reader.get_candles = AsyncMock(  # type: ignore[method-assign]
                side_effect=AssertionError("should not hit HL"),
            )

            page = await service.get_candle_page("BTC", "1h", limit=5)
            assert len(page) == 5
            # Oldest-first ordering — pagination relies on it.
            timestamps = [row["timestamp_ms"] for row in page]
            assert timestamps == sorted(timestamps)
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_backfills_older_range_on_cursor_page(
        self,
        tmp_path: Path,
    ) -> None:
        """A cursor before the cache's oldest bar triggers a backfill."""
        service = await _make_service(tmp_path)
        try:
            now_ms = int(time.time() * 1000)
            interval_ms = 3_600_000
            # Cache holds the newest 5 bars.
            cache_bars = [
                _bar("BTC", "1h", now_ms - i * interval_ms) for i in range(5)
            ]
            await service._upsert_batch(cache_bars)  # noqa: SLF001

            # The simulated HL response covers the older 10 bars the
            # cursor will reach into. The service should call the reader
            # exactly once and persist the returned bars.
            cursor = now_ms - 5 * interval_ms  # equal to cache's oldest ts
            older_bars = [
                _bar("BTC", "1h", cursor - (i + 1) * interval_ms) for i in range(10)
            ]
            mock_reader = AsyncMock(return_value=older_bars)
            service._reader.get_candles = mock_reader  # type: ignore[method-assign]

            page = await service.get_candle_page(
                "BTC", "1h", before_ms=cursor, limit=10
            )

            assert len(page) == 10
            # No bar in the page should be at or after the cursor.
            assert all(row["timestamp_ms"] < cursor for row in page)
            assert mock_reader.await_count == 1
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_backfill_stops_when_exchange_returns_empty(
        self,
        tmp_path: Path,
    ) -> None:
        """HL returning [] means the asset has no deeper history — stop cleanly."""
        service = await _make_service(tmp_path)
        try:
            service._reader.get_candles = AsyncMock(return_value=[])  # type: ignore[method-assign]
            page = await service.get_candle_page(
                "NEWCOIN", "1h", before_ms=1_000_000, limit=500
            )
            assert page == []
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_initial_load_tops_up_stale_cache(
        self,
        tmp_path: Path,
    ) -> None:
        """``before_ms=None`` with a stale cache triggers a top-up fetch."""
        service = await _make_service(tmp_path)
        try:
            now_ms = int(time.time() * 1000)
            interval_ms = 3_600_000
            # Cache ends 10 hours ago — older than the 2-interval threshold.
            stale_bars = [
                _bar("BTC", "1h", now_ms - (10 + i) * interval_ms) for i in range(3)
            ]
            await service._upsert_batch(stale_bars)  # noqa: SLF001

            fresh_bars = [_bar("BTC", "1h", now_ms - i * interval_ms) for i in range(3)]
            mock_reader = AsyncMock(return_value=fresh_bars)
            service._reader.get_candles = mock_reader  # type: ignore[method-assign]

            page = await service.get_candle_page("BTC", "1h", limit=20)
            assert mock_reader.await_count >= 1
            # The returned page must include both the freshly topped-up
            # bars and the previously cached ones.
            ts = {row["timestamp_ms"] for row in page}
            assert (now_ms - 0 * interval_ms) in ts
            assert (now_ms - 10 * interval_ms) in ts
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_safety_cap_bounds_backfill_chunks(
        self,
        tmp_path: Path,
    ) -> None:
        """Infinite HL loops don't survive the ``max_backfill_chunks`` cap."""
        service = await _make_service(tmp_path)
        try:
            interval_ms = 3_600_000
            call_count = 0

            async def fake_get_candles(
                coin: str, interval: str, start_ms: int, end_ms: int
            ) -> list[CandleBar]:
                nonlocal call_count
                call_count += 1
                # Return one bar at the window's oldest edge so the
                # anchor advances by one per call — forces the loop
                # to actually hit the cap rather than bailing early
                # on the "no progress" branch.
                return [_bar("BTC", "1h", end_ms - interval_ms)]

            service._reader.get_candles = fake_get_candles  # type: ignore[assignment]

            cursor = 10_000_000_000  # arbitrary far-future ms
            target_bars = 100_000  # larger than cap * chunk size
            await service.get_candle_page(
                "BTC", "1h", before_ms=cursor, limit=target_bars
            )
            assert call_count <= service._max_backfill_chunks  # noqa: SLF001
        finally:
            await service.close()
