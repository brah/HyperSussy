"""HyperLiquid REST client implementing ExchangeReader.

Wraps the SDK's Info class with rate limiting and domain model
conversion.  Supports both native (validator) and HIP-3
(builder-deployed) perpetual markets.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from hyperliquid.info import Info

from hypersussy.exchange.hyperliquid.parsers import (
    parse_candles,
    parse_funding_history,
    parse_l2_snapshot,
    parse_meta_and_asset_ctxs,
    parse_user_fills,
    parse_user_state,
)
from hypersussy.models import (
    AssetSnapshot,
    CandleBar,
    FundingRate,
    L2Book,
    Position,
    Trade,
)
from hypersussy.rate_limiter import WeightRateLimiter

logger = logging.getLogger(__name__)

_INFO_PATH = "/info"


class HyperLiquidReader:
    """Async wrapper around the HL SDK Info class with rate limiting.

    Args:
        base_url: HL API base URL.
        rate_limiter: Shared rate limiter instance.
        include_hip3: Fetch HIP-3 builder-deployed perpetuals.
        hip3_dex_filter: If non-empty, only include these HIP-3 dexes.
    """

    def __init__(
        self,
        base_url: str = "https://api.hyperliquid.xyz",
        rate_limiter: WeightRateLimiter | None = None,
        include_hip3: bool = True,
        hip3_dex_filter: list[str] | None = None,
    ) -> None:
        self._info = Info(base_url=base_url, skip_ws=True)
        self._limiter = rate_limiter or WeightRateLimiter()
        self._include_hip3 = include_hip3
        self._hip3_dex_filter: set[str] = set(hip3_dex_filter or [])
        self._hip3_dex_names: list[str] = []
        # Cap concurrent HTTP requests to avoid 429s from burst traffic.
        # The weight limiter prevents per-minute exhaustion; this prevents
        # simultaneous bursts that the API rejects regardless of weight.
        self._concurrency = asyncio.Semaphore(4)

    async def _run_sync(self, func: partial[Any], weight: int) -> Any:
        """Run a synchronous SDK call in an executor with rate limiting.

        Acquires both the concurrency semaphore (max 4 in-flight) and the
        weight-based rate limiter before dispatching to a thread executor.

        Args:
            func: Partial-applied SDK method.
            weight: API weight cost.

        Returns:
            The SDK method's return value.
        """
        logger.debug("_run_sync: waiting for concurrency semaphore (weight=%d)", weight)
        async with self._concurrency:
            logger.debug("_run_sync: semaphore acquired, awaiting rate limiter")
            await self._limiter.acquire(weight)
            logger.debug("_run_sync: dispatching to executor")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, func)
            logger.debug("_run_sync: executor returned")
            return result

    async def refresh_hip3_dexes(self) -> list[str]:
        """Fetch and cache the list of active HIP-3 builder dex names.

        Returns:
            List of dex name strings (e.g. ["xyz", "flx", "km"]).
        """
        raw = await self._run_sync(partial(self._info.perp_dexs), weight=2)
        names: list[str] = []
        for entry in raw:
            if entry is None:
                continue
            name = entry.get("name", "")
            if not name:
                continue
            if self._hip3_dex_filter and name not in self._hip3_dex_filter:
                continue
            names.append(name)
        self._hip3_dex_names = names
        logger.info("HIP-3 dexes: %d active (%s)", len(names), ", ".join(names))
        return names

    async def get_asset_snapshots(self) -> list[AssetSnapshot]:
        """Fetch all perpetual assets with OI, volume, prices, funding.

        Includes both native and HIP-3 builder-deployed markets when
        ``include_hip3`` is enabled.

        Returns:
            Snapshot for every listed perpetual asset.
        """
        if self._include_hip3 and not self._hip3_dex_names:
            logger.debug("get_asset_snapshots: refreshing HIP-3 dex list")
            await self.refresh_hip3_dexes()

        dexes = [""] + (self._hip3_dex_names if self._include_hip3 else [])
        logger.debug("get_asset_snapshots: fetching %d dex(es)", len(dexes))
        snapshots: list[AssetSnapshot] = []
        for i, dex in enumerate(dexes):
            label = dex or "native"
            logger.debug(
                "get_asset_snapshots: fetching dex %d/%d (%s)",
                i + 1,
                len(dexes),
                label,
            )
            try:
                snapshots.extend(await self._fetch_dex_snapshots(dex))
            except Exception:
                logger.exception("Failed to fetch dex snapshots for %r", dex)
        logger.debug(
            "get_asset_snapshots: done — %d snapshots across %d dex(es)",
            len(snapshots),
            len(dexes),
        )
        return snapshots

    async def _fetch_dex_snapshots(self, dex: str) -> list[AssetSnapshot]:
        """Fetch metaAndAssetCtxs for a single dex.

        Args:
            dex: Dex name ("" for native, e.g. "xyz" for HIP-3).

        Returns:
            Parsed asset snapshots for this dex.
        """
        payload: dict[str, str] = {"type": "metaAndAssetCtxs"}
        if dex:
            payload["dex"] = dex
        raw = await self._run_sync(
            partial(self._info.post, _INFO_PATH, payload), weight=2
        )
        return parse_meta_and_asset_ctxs(raw)

    async def get_user_positions(
        self,
        address: str,
        active_dexes: set[str] | None = None,
    ) -> list[Position]:
        """Fetch open positions for a given address across relevant dexes.

        Args:
            address: The 0x user address.
            active_dexes: HIP-3 dex prefixes the address has traded on.
                ``None`` queries all known dexes. An empty set queries
                native only. A non-empty set queries native + intersection
                with known dexes to filter stale/unrecognized prefixes.

        Returns:
            All open positions for the user.
        """
        if not self._include_hip3:
            dexes: list[str] = [""]
        elif active_dexes is None:
            dexes = [""] + self._hip3_dex_names
        else:
            hip3_to_query = sorted(active_dexes & set(self._hip3_dex_names))
            dexes = [""] + hip3_to_query

        results = await asyncio.gather(
            *(self._fetch_user_positions(address, dex) for dex in dexes),
            return_exceptions=True,
        )

        positions: list[Position] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Failed to fetch positions from a dex: %s", result)
                continue
            positions.extend(result)
        return positions

    async def _fetch_user_positions(self, address: str, dex: str) -> list[Position]:
        """Fetch positions for a user on a single dex.

        Args:
            address: The 0x user address.
            dex: Dex name ("" for native).

        Returns:
            Positions on this dex.
        """
        raw = await self._run_sync(
            partial(self._info.user_state, address, dex=dex), weight=2
        )
        return parse_user_state(raw, address)

    async def get_user_fills(
        self,
        address: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[Trade]:
        """Fetch historical fills for a user.

        Args:
            address: The 0x user address.
            start_ms: Start timestamp filter (inclusive).
            end_ms: End timestamp filter (inclusive).

        Returns:
            List of trade fills.
        """
        if start_ms is not None:
            raw = await self._run_sync(
                partial(
                    self._info.user_fills_by_time,
                    address,
                    start_ms,
                    end_ms,
                ),
                weight=20,
            )
        else:
            raw = await self._run_sync(
                partial(self._info.user_fills, address), weight=20
            )
        return parse_user_fills(raw, address)

    async def get_l2_book(self, coin: str) -> L2Book:
        """Fetch a 20-level order book snapshot.

        Uses a raw POST to bypass the SDK's ``name_to_coin`` lookup,
        which only covers dexes loaded at init time.

        Args:
            coin: Asset name (e.g. "BTC", "xyz:XYZ100").

        Returns:
            L2 book with bids and asks.
        """
        raw = await self._run_sync(
            partial(self._info.post, _INFO_PATH, {"type": "l2Book", "coin": coin}),
            weight=2,
        )
        return parse_l2_snapshot(raw)

    async def get_candles(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[CandleBar]:
        """Fetch OHLCV candle data.

        Args:
            coin: Asset name.
            interval: Candle interval (e.g. "1m", "5m", "1h").
            start_ms: Start timestamp in milliseconds.
            end_ms: End timestamp in milliseconds.

        Returns:
            List of candle bars.
        """
        raw = await self._run_sync(
            partial(
                self._info.candles_snapshot,
                coin,
                interval,
                start_ms,
                end_ms,
            ),
            weight=20,
        )
        return parse_candles(raw, coin, interval)

    async def get_user_twap_slice_fills(
        self,
        address: str,
    ) -> list[dict[str, object]]:
        """Fetch the most recent TWAP slice fills for a user.

        Args:
            address: The 0x user address.

        Returns:
            Up to 2000 most recent TWAP slice fill dicts, each containing
            a ``fill`` sub-dict and a ``twapId`` field.
        """
        raw = await self._run_sync(
            partial(self._info.user_twap_slice_fills, address), weight=2
        )
        return list(raw) if raw else []

    async def get_recent_funding(
        self,
        coin: str,
        start_ms: int,
        end_ms: int | None = None,
    ) -> list[FundingRate]:
        """Fetch historical funding rate entries.

        Uses a raw POST to bypass the SDK's ``name_to_coin`` lookup,
        which only covers dexes loaded at init time.

        Args:
            coin: Asset name (e.g. "BTC", "xyz:XYZ100").
            start_ms: Start timestamp in milliseconds.
            end_ms: End timestamp in milliseconds (optional).

        Returns:
            List of funding rate entries.
        """
        payload: dict[str, str | int] = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": start_ms,
        }
        if end_ms is not None:
            payload["endTime"] = end_ms
        raw = await self._run_sync(
            partial(self._info.post, _INFO_PATH, payload), weight=20
        )
        return parse_funding_history(raw, coin)
