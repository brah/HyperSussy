"""Protocol definitions for exchange data access.

These protocols abstract the exchange-specific wire protocol so that
detection engines only depend on domain models, enabling multi-DEX
extensibility.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from hypersussy.models import (
    AssetSnapshot,
    CandleBar,
    FundingRate,
    L2Book,
    Position,
    Trade,
)


class ExchangeReader(Protocol):
    """Read-only market and account data from a perpetual DEX."""

    async def get_asset_snapshots(self) -> list[AssetSnapshot]:
        """Fetch all assets with OI, volume, prices, and funding.

        Returns:
            Snapshot for every listed perpetual asset.
        """
        ...

    async def get_user_positions(
        self,
        address: str,
        active_dexes: set[str] | None = None,
    ) -> list[Position]:
        """Fetch open positions for a given address.

        Args:
            address: The 0x user address.
            active_dexes: HIP-3 dex prefixes the address has traded on.
                ``None`` queries all known dexes (safe default for new
                addresses). An empty set queries native only. A non-empty
                set queries native + the intersection with known dexes.

        Returns:
            All open positions for the user.
        """
        ...

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
        ...

    async def get_l2_book(self, coin: str) -> L2Book:
        """Fetch a 20-level order book snapshot.

        Args:
            coin: Asset name (e.g. "BTC", "ETH").

        Returns:
            L2 book with bids and asks.
        """
        ...

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
        ...

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
        ...

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
        ...


class ExchangeStream(Protocol):
    """Real-time streaming from a perpetual DEX."""

    async def stream_trades(self, coin: str) -> AsyncIterator[Trade]:
        """Yield trades in real time for a coin.

        Args:
            coin: Asset name.

        Yields:
            Each trade as it occurs.
        """
        ...

    async def stream_all_mids(
        self,
    ) -> AsyncIterator[dict[str, float]]:
        """Yield mid-price updates for all assets.

        Yields:
            Dict mapping coin name to mid price.
        """
        ...

    async def stream_l2_book(self, coin: str) -> AsyncIterator[L2Book]:
        """Yield L2 book updates for a coin.

        Args:
            coin: Asset name.

        Yields:
            Updated L2 book snapshots.
        """
        ...
