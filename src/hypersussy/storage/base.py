"""Storage protocol for persistent data access."""

from __future__ import annotations

from typing import Protocol

from hypersussy.models import (
    Alert,
    AssetSnapshot,
    CandleBar,
    Position,
    Trade,
)


class StorageProtocol(Protocol):
    """Abstract storage interface for all persistent data."""

    async def init(self) -> None:
        """Initialize the storage backend (create tables, etc.)."""
        ...

    async def close(self) -> None:
        """Close the storage backend gracefully."""
        ...

    # -- Asset snapshots --

    async def insert_asset_snapshots(self, snapshots: list[AssetSnapshot]) -> None:
        """Batch insert asset snapshots.

        Args:
            snapshots: List of asset snapshots to store.
        """
        ...

    async def get_oi_history(self, coin: str, since_ms: int) -> list[AssetSnapshot]:
        """Fetch recent OI history for a coin.

        Args:
            coin: Asset name.
            since_ms: Absolute start timestamp in milliseconds.

        Returns:
            Snapshots ordered by timestamp ascending.
        """
        ...

    # -- Trades --

    async def insert_trades(self, trades: list[Trade]) -> None:
        """Batch insert trades (ignores duplicates by tid).

        Args:
            trades: List of trades to store.
        """
        ...

    async def get_top_addresses_by_volume(
        self,
        coin: str,
        since_ms: int,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Get top trading addresses by notional volume.

        Args:
            coin: Asset name.
            since_ms: Start timestamp.
            limit: Max addresses to return.

        Returns:
            List of (address, total_volume_usd) tuples, descending.
        """
        ...

    async def get_trades_by_address(self, address: str, since_ms: int) -> list[Trade]:
        """Fetch trades for a specific address since a timestamp.

        Args:
            address: The 0x address (as buyer or seller).
            since_ms: Start timestamp.

        Returns:
            List of trades ordered by timestamp.
        """
        ...

    # -- Tracked addresses --

    async def upsert_tracked_address(
        self,
        address: str,
        label: str,
        source: str,
        volume_usd: float,
    ) -> None:
        """Insert or update a tracked whale address.

        Args:
            address: The 0x address.
            label: Human-readable label.
            source: Discovery source (e.g. "discovered").
            volume_usd: Cumulative volume.
        """
        ...

    async def get_tracked_addresses(self) -> list[str]:
        """Get all tracked whale addresses.

        Returns:
            List of 0x addresses.
        """
        ...

    async def delete_tracked_address(self, address: str) -> None:
        """Remove a tracked whale address.

        Args:
            address: The 0x address to remove.
        """
        ...

    # -- Positions --

    async def insert_positions(self, positions: list[Position]) -> None:
        """Batch insert position snapshots.

        Args:
            positions: List of position snapshots.
        """
        ...

    async def get_position_history(
        self, address: str, coin: str, since_ms: int
    ) -> list[Position]:
        """Fetch position history for an address on a coin.

        Args:
            address: The 0x address.
            coin: Asset name.
            since_ms: Absolute start timestamp in milliseconds.

        Returns:
            Positions ordered by timestamp ascending.
        """
        ...

    # -- Alerts --

    async def insert_alert(self, alert: Alert) -> None:
        """Store a generated alert.

        Args:
            alert: The alert to persist.
        """
        ...

    async def get_recent_alerts(
        self,
        alert_type: str,
        coin: str,
        since_ms: int,
    ) -> list[Alert]:
        """Fetch recent alerts for deduplication checks.

        Args:
            alert_type: Engine alert type string.
            coin: Asset name.
            since_ms: Start timestamp.

        Returns:
            Matching alerts ordered by timestamp.
        """
        ...

    async def get_latest_positions(self, address: str) -> list[Position]:
        """Get the most recent position snapshot per coin for an address.

        Args:
            address: The 0x address.

        Returns:
            Latest position per coin (one entry per coin).
        """
        ...

    async def get_total_volume(self, coin: str, since_ms: int) -> float:
        """Get total trade volume for a coin since a timestamp.

        Args:
            coin: Asset name.
            since_ms: Start timestamp.

        Returns:
            Total notional volume in USD.
        """
        ...

    # -- Candles --

    async def insert_candles(self, candles: list[CandleBar]) -> None:
        """Batch insert candle data (upsert on conflict).

        Args:
            candles: List of candle bars.
        """
        ...

    async def get_candles(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> list[CandleBar]:
        """Fetch cached candle data.

        Args:
            coin: Asset name.
            interval: Candle interval string.
            start_ms: Start timestamp.
            end_ms: End timestamp.

        Returns:
            Candle bars ordered by timestamp.
        """
        ...
