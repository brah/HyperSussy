"""Realized PnL computation from Hyperliquid user fills.

Fetches fill history via the HL REST API and sums the ``closedPnl``
field that the exchange attaches to each fill.  Results are cached
per address with a short TTL to avoid redundant upstream calls.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from hypersussy.api._address_cache import TtlAddressCache
from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.rate_limiter import WeightRateLimiter

_CACHE_TTL_S = 120.0
# Hard cap on distinct addresses retained in the per-process PnL cache.
# Paired with on-insert TTL eviction in TtlAddressCache, this bounds
# memory growth in long-running sessions that search many distinct
# wallets.
_CACHE_MAX_ENTRIES = 512
_HL_FILL_CAP = 2000
_MAX_PNL_PAGES = 10  # safety cap: 10 pages x 2000 = 20k fills max
_INITIAL_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class PnlResult:
    """Aggregated realized PnL for a single time window.

    Args:
        realized_pnl: Sum of closedPnl across all fills.
        fill_count: Number of fills with a non-null closedPnl.
        is_complete: False if the page cap was hit and the total
            may be understated.
    """

    realized_pnl: float
    fill_count: int
    is_complete: bool = True


@dataclass(frozen=True, slots=True)
class PnlSnapshot:
    """Combined 7-day and all-time PnL for a wallet."""

    pnl_7d: PnlResult
    pnl_all_time: PnlResult


class PnlService:
    """Fetches and aggregates realized PnL for a wallet address.

    Both the 7-day and all-time windows are fetched concurrently in a
    single ``get_pnl`` call.  Results are cached per address for
    ``_CACHE_TTL_S`` seconds to avoid hitting the HL API on every
    wallet-detail render.

    Args:
        base_url: Hyperliquid API base URL.
    """

    def __init__(self, base_url: str = "https://api.hyperliquid.xyz") -> None:
        self._reader = HyperLiquidReader(
            base_url=base_url,
            rate_limiter=WeightRateLimiter(max_weight=200, window_seconds=60),
            include_hip3=False,
        )
        self._cache: TtlAddressCache[PnlSnapshot] = TtlAddressCache(
            ttl_seconds=_CACHE_TTL_S,
            max_entries=_CACHE_MAX_ENTRIES,
        )

    async def get_pnl(self, address: str) -> PnlSnapshot:
        """Fetch 7-day and all-time realized PnL concurrently.

        Args:
            address: The 0x wallet address.

        Returns:
            PnlSnapshot with both time windows.
        """
        cached = self._cache.get(address)
        if cached is not None:
            return cached

        # NOTE: time.time() is wall-clock and is intentionally used for
        # the HL API ``start_ms`` filter (HL expects epoch milliseconds).
        # The cache TTL inside ``TtlAddressCache`` uses time.monotonic().
        seven_d_ms = int((time.time() - 7 * 86_400) * 1000)
        pnl_7d, pnl_all = await asyncio.gather(
            self._fetch_pnl(address, seven_d_ms),
            self._fetch_pnl(address, 0),
        )
        snapshot = PnlSnapshot(pnl_7d=pnl_7d, pnl_all_time=pnl_all)
        self._cache.put(address, snapshot)
        return snapshot

    async def _fetch_pnl(self, address: str, start_ms: int) -> PnlResult:
        """Fetch all fills from HL and sum closedPnl.

        Walks backward through time windows when the API returns
        its 2000-fill cap, so the aggregation covers the full
        history rather than just the most recent page.

        Args:
            address: The 0x wallet address.
            start_ms: Start timestamp filter (0 for all-time).

        Returns:
            Aggregated PnlResult.
        """
        total_pnl = 0.0
        count = 0
        complete = True
        end_ms: int | None = None  # None = now

        for page_idx in range(_MAX_PNL_PAGES):
            # Wall-clock — HL fill timestamps are epoch ms, so the upper
            # bound has to be in the same domain.
            raw = await self._fetch_raw_fills(
                address,
                start_ms,
                end_ms or int(time.time() * 1000),
            )
            if not raw:
                break

            for fill in raw:
                closed = fill.get("closedPnl")
                if closed is not None:
                    total_pnl += float(closed)
                    count += 1

            if len(raw) < _HL_FILL_CAP:
                break

            # Move the window backward past the oldest fill.
            oldest = min(int(f.get("time", 0)) for f in raw)
            if end_ms is not None and oldest >= end_ms:
                complete = False
                break  # no progress — avoid infinite loop
            end_ms = oldest

            # Hit the safety cap on the last iteration.
            if page_idx == _MAX_PNL_PAGES - 1:
                complete = False

        return PnlResult(
            realized_pnl=total_pnl,
            fill_count=count,
            is_complete=complete,
        )

    async def get_fills(
        self,
        address: str,
        before_ms: int | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch a page of fills for an address, newest first.

        Uses a narrowing time-window strategy: starts with a 30-day
        window and widens only if needed, to avoid scanning all-time
        on every request.

        Args:
            address: The 0x wallet address.
            before_ms: Cursor — only fills before this timestamp.
                ``None`` means start from now.
            limit: Maximum fills to return per page.

        Returns:
            Tuple of (fills_list, next_cursor). ``next_cursor`` is the
            oldest ``time`` in the page for the next request, or
            ``None`` if no more fills exist.
        """
        # Wall-clock — HL fill timestamps are epoch ms.
        end_ms = before_ms or int(time.time() * 1000)

        # Try a narrow window first to keep the API call cheap.
        start_ms = end_ms - _INITIAL_WINDOW_DAYS * 86_400_000
        raw = await self._fetch_raw_fills(address, max(start_ms, 0), end_ms)

        # Track whether we've actually scanned from the beginning of
        # time. Two paths set it True: (1) the narrow window already
        # extends to epoch 0 (deep pagination), (2) we explicitly
        # widen below because the narrow window was under-full.
        scanned_all_time = start_ms <= 0

        # If the narrow window returned fewer than limit and didn't
        # hit the API cap, widen to all-time to find older fills.
        if len(raw) < limit and len(raw) < _HL_FILL_CAP and not scanned_all_time:
            raw = await self._fetch_raw_fills(address, 0, end_ms)
            scanned_all_time = True

        # Sort newest-first, slice to limit.
        raw.sort(key=lambda f: f.get("time", 0), reverse=True)
        page = raw[:limit]

        next_cursor: int | None = None
        if page:
            oldest_time = page[-1].get("time", 0)
            sliced_off = len(raw) > len(page)
            api_capped = len(raw) >= _HL_FILL_CAP
            # Narrow window filled exactly to ``limit`` without
            # widening: we don't actually know whether older fills
            # exist outside the 30-day window. Return the cursor so
            # the client can probe — the next call will widen if the
            # probe's narrow window comes back under-full.
            narrow_may_hide_older = not scanned_all_time and len(raw) >= limit
            if sliced_off or api_capped or narrow_may_hide_older:
                next_cursor = oldest_time

        fills = [self._normalize_fill(f) for f in page]
        return fills, next_cursor

    async def _fetch_raw_fills(
        self,
        address: str,
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        """Fetch raw fill dicts from the HL API.

        Args:
            address: The 0x wallet address.
            start_ms: Start of time window (inclusive).
            end_ms: End of time window (exclusive).

        Returns:
            Raw fill dicts from the API.
        """
        raw = await self._reader._call_info(
            "user_fills_by_time",
            lambda: self._reader._info_client.user_fills_by_time(
                address,
                start_ms,
                end_time=end_ms,
            ),
            weight=20,
            context=f"fills:{address}",
        )
        return list(raw) if raw else []

    @staticmethod
    def _normalize_fill(raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a raw HL fill dict to the API response shape.

        Args:
            raw: Raw fill dict from the HL API.

        Returns:
            Normalized dict matching FillItem schema.
        """
        return {
            "coin": raw.get("coin", ""),
            "side": raw.get("side", ""),
            "dir": raw.get("dir", ""),
            "px": float(raw.get("px", 0)),
            "sz": float(raw.get("sz", 0)),
            "closed_pnl": float(raw.get("closedPnl", 0)),
            "start_position": float(raw.get("startPosition", 0)),
            "oid": int(raw.get("oid", 0)),
            "hash": raw.get("hash", ""),
            "time": int(raw.get("time", 0)),
            "crossed": bool(raw.get("crossed", False)),
        }
