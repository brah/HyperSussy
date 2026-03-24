"""HyperLiquid REST client implementing ExchangeReader.

Wraps the SDK's Info class with rate limiting and domain model
conversion.
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


class HyperLiquidReader:
    """Async wrapper around the HL SDK Info class with rate limiting.

    Args:
        base_url: HL API base URL.
        rate_limiter: Shared rate limiter instance.
    """

    def __init__(
        self,
        base_url: str = "https://api.hyperliquid.xyz",
        rate_limiter: WeightRateLimiter | None = None,
    ) -> None:
        self._info = Info(base_url=base_url, skip_ws=True)
        self._limiter = rate_limiter or WeightRateLimiter()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _run_sync(self, func: partial[Any], weight: int) -> Any:
        """Run a synchronous SDK call in an executor with rate limiting.

        Args:
            func: Partial-applied SDK method.
            weight: API weight cost.

        Returns:
            The SDK method's return value.
        """
        await self._limiter.acquire(weight)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)

    async def get_asset_snapshots(self) -> list[AssetSnapshot]:
        """Fetch all perpetual assets with OI, volume, prices, funding.

        Returns:
            Snapshot for every listed perpetual asset.
        """
        raw = await self._run_sync(partial(self._info.meta_and_asset_ctxs), weight=2)
        return parse_meta_and_asset_ctxs(raw)

    async def get_user_positions(self, address: str) -> list[Position]:
        """Fetch open positions for a given address.

        Args:
            address: The 0x user address.

        Returns:
            All open positions for the user.
        """
        raw = await self._run_sync(partial(self._info.user_state, address), weight=2)
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

        Args:
            coin: Asset name (e.g. "BTC", "ETH").

        Returns:
            L2 book with bids and asks.
        """
        raw = await self._run_sync(partial(self._info.l2_snapshot, coin), weight=2)
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

    async def get_recent_funding(
        self,
        coin: str,
        start_ms: int,
        end_ms: int | None = None,
    ) -> list[FundingRate]:
        """Fetch historical funding rate entries.

        Args:
            coin: Asset name.
            start_ms: Start timestamp in milliseconds.
            end_ms: End timestamp in milliseconds (optional).

        Returns:
            List of funding rate entries.
        """
        raw = await self._run_sync(
            partial(self._info.funding_history, coin, start_ms, end_ms),
            weight=20,
        )
        return parse_funding_history(raw, coin)
