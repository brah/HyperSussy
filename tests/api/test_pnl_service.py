"""Tests for the PnL service: aggregation, caching, and error handling."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.api._address_cache import TtlAddressCache
from hypersussy.api.pnl_service import PnlResult, PnlService, PnlSnapshot


def _fill(
    closed_pnl: str | None = "100.0",
    ts: int | None = None,
) -> dict[str, Any]:
    """Build a minimal fill dict."""
    d: dict[str, Any] = {
        "coin": "BTC",
        "side": "B",
        "dir": "Open Long",
        "px": "50000.0",
        "sz": "1.0",
        "time": ts if ts is not None else int(time.time() * 1000),
        "hash": "0xabc",
        "tid": 1,
        "oid": 42,
        "crossed": True,
        "startPosition": "0.0",
    }
    if closed_pnl is not None:
        d["closedPnl"] = closed_pnl
    return d


def _make_service() -> PnlService:
    """Create a PnlService with a mocked HL reader."""
    service = PnlService.__new__(PnlService)
    service._reader = MagicMock()
    service._reader._call_info = AsyncMock(return_value=[])
    service._reader._info_client = MagicMock()
    # Use the same TtlAddressCache the production constructor uses
    # so the expiry/eviction code paths exercise the real shape.
    service._cache = TtlAddressCache(ttl_seconds=120.0, max_entries=512)
    return service


class TestFetchPnl:
    """Unit tests for _fetch_pnl aggregation logic."""

    @pytest.mark.asyncio
    async def test_sums_closed_pnl(self) -> None:
        """Fills with closedPnl are summed correctly."""
        service = _make_service()
        fills = [_fill("150.50"), _fill("-30.25"), _fill("80.00")]
        service._reader._call_info = AsyncMock(return_value=fills)

        result = await service._fetch_pnl("0x" + "a" * 40, 0)

        assert isinstance(result, PnlResult)
        assert abs(result.realized_pnl - 200.25) < 0.01
        assert result.fill_count == 3

    @pytest.mark.asyncio
    async def test_skips_null_closed_pnl(self) -> None:
        """Fills without closedPnl are excluded from the sum."""
        service = _make_service()
        fills = [_fill("100.0"), _fill(None)]
        service._reader._call_info = AsyncMock(return_value=fills)

        result = await service._fetch_pnl("0x" + "a" * 40, 0)

        assert abs(result.realized_pnl - 100.0) < 0.01
        assert result.fill_count == 1

    @pytest.mark.asyncio
    async def test_empty_fills(self) -> None:
        """No fills returns zero PnL."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=[])

        result = await service._fetch_pnl("0x" + "a" * 40, 0)

        assert result.realized_pnl == 0.0
        assert result.fill_count == 0

    @pytest.mark.asyncio
    async def test_none_response(self) -> None:
        """API returning None is treated as empty."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=None)

        result = await service._fetch_pnl("0x" + "a" * 40, 0)

        assert result.realized_pnl == 0.0
        assert result.fill_count == 0


class TestGetPnl:
    """Integration tests for get_pnl including caching."""

    @pytest.mark.asyncio
    async def test_returns_snapshot_with_both_windows(self) -> None:
        """get_pnl returns a PnlSnapshot with 7d and all-time."""
        service = _make_service()
        fills = [_fill("500.0")]
        service._reader._call_info = AsyncMock(return_value=fills)

        snapshot = await service.get_pnl("0x" + "a" * 40)

        assert isinstance(snapshot, PnlSnapshot)
        assert abs(snapshot.pnl_7d.realized_pnl - 500.0) < 0.01
        assert abs(snapshot.pnl_all_time.realized_pnl - 500.0) < 0.01

    @pytest.mark.asyncio
    async def test_calls_api_concurrently(self) -> None:
        """Both time windows are fetched in a single gather."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=[])

        await service.get_pnl("0x" + "a" * 40)

        # Two calls: one for 7d, one for all-time
        assert service._reader._call_info.await_count == 2

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self) -> None:
        """Second call within TTL uses cache, no API calls."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=[_fill("10.0")])

        first = await service.get_pnl("0x" + "a" * 40)
        service._reader._call_info.reset_mock()

        second = await service.get_pnl("0x" + "a" * 40)

        assert first is second
        service._reader._call_info.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_expired_refetches(self) -> None:
        """Expired cache entry triggers a fresh API fetch."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=[_fill("10.0")])

        await service.get_pnl("0x" + "a" * 40)
        # Forcibly expire every entry by reaching into the cache's
        # private OrderedDict — the test needs to fast-forward time
        # without sleeping, and TtlAddressCache has no public knob.
        for entry in service._cache._cache.values():
            entry.expires_at = 0.0
        service._reader._call_info.reset_mock()
        service._reader._call_info = AsyncMock(return_value=[_fill("20.0")])

        snapshot = await service.get_pnl("0x" + "a" * 40)

        assert service._reader._call_info.await_count == 2
        assert abs(snapshot.pnl_7d.realized_pnl - 20.0) < 0.01

    @pytest.mark.asyncio
    async def test_upstream_error_propagates(self) -> None:
        """HL API errors are not swallowed."""
        service = _make_service()
        service._reader._call_info = AsyncMock(
            side_effect=RuntimeError("429 rate limited")
        )

        with pytest.raises(RuntimeError, match="429"):
            await service.get_pnl("0x" + "a" * 40)


class TestGetFills:
    """Tests for paginated fill history."""

    @pytest.mark.asyncio
    async def test_returns_page_sorted_newest_first(self) -> None:
        """Fills are returned newest-first within the page."""
        service = _make_service()
        fills = [_fill(ts=1000), _fill(ts=3000), _fill(ts=2000)]
        service._reader._call_info = AsyncMock(return_value=fills)

        page, cursor = await service.get_fills("0x" + "a" * 40, limit=10)

        times = [f["time"] for f in page]
        assert times == [3000, 2000, 1000]

    @pytest.mark.asyncio
    async def test_slices_to_limit(self) -> None:
        """Only limit fills are returned even if API returns more."""
        service = _make_service()
        fills = [_fill(ts=i) for i in range(100, 110)]
        service._reader._call_info = AsyncMock(return_value=fills)

        page, cursor = await service.get_fills("0x" + "a" * 40, limit=3)

        assert len(page) == 3
        assert cursor is not None

    @pytest.mark.asyncio
    async def test_no_more_pages(self) -> None:
        """Cursor is None when fewer than limit fills returned."""
        service = _make_service()
        fills = [_fill(ts=1000), _fill(ts=2000)]
        service._reader._call_info = AsyncMock(return_value=fills)

        page, cursor = await service.get_fills("0x" + "a" * 40, limit=50)

        assert len(page) == 2
        assert cursor is None

    @pytest.mark.asyncio
    async def test_empty_fills(self) -> None:
        """Empty response returns empty page with no cursor."""
        service = _make_service()
        service._reader._call_info = AsyncMock(return_value=[])

        page, cursor = await service.get_fills("0x" + "a" * 40, limit=50)

        assert page == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_narrow_window_full_page_returns_cursor(self) -> None:
        """Narrow window filled exactly to limit must return a cursor.

        Regression: with the 30-day narrow window returning exactly
        ``limit`` fills, the old formula concluded no older fills
        existed and returned ``cursor=None`` — silently hiding any
        fills older than 30 days. The correct behaviour is to return
        the oldest timestamp as a cursor so the client can probe
        deeper; the next call will widen if the probe is under-full.
        """
        service = _make_service()
        now_ms = int(time.time() * 1000)
        # All fills within the last 30 days. Returned count == limit.
        fills = [_fill(ts=now_ms - i * 1000) for i in range(50)]
        service._reader._call_info = AsyncMock(return_value=fills)

        page, cursor = await service.get_fills("0x" + "a" * 40, limit=50)

        assert len(page) == 50
        assert cursor is not None, (
            "Narrow window was full; client cannot know older fills "
            "don't exist. A cursor must be returned so the next call "
            "can probe the wider window."
        )

    @pytest.mark.asyncio
    async def test_normalizes_fill_fields(self) -> None:
        """Raw HL fields are normalized to the API schema shape."""
        service = _make_service()
        fills = [_fill(closed_pnl="250.50", ts=5000)]
        service._reader._call_info = AsyncMock(return_value=fills)

        page, _ = await service.get_fills("0x" + "a" * 40, limit=10)

        f = page[0]
        assert f["coin"] == "BTC"
        assert f["closed_pnl"] == 250.50
        assert f["dir"] == "Open Long"
        assert f["time"] == 5000
        assert f["crossed"] is True
