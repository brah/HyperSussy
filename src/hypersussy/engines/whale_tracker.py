"""Whale discovery and position tracking engine.

Passively discovers high-volume addresses from the trade stream,
promotes them to a tracked list, and periodically polls their
positions to detect large or changing holdings.
"""

from __future__ import annotations

import logging

from hypersussy.config import HyperSussySettings
from hypersussy.engines.position_census import PositionCensus
from hypersussy.engines.position_tracker import PositionTracker
from hypersussy.engines.twap_detector import TwapDetector
from hypersussy.engines.whale_discovery import WhaleDiscovery
from hypersussy.exchange.base import ExchangeReader
from hypersussy.models import Alert, AssetSnapshot, Position, Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class WhaleTrackerEngine:
    """Discover whales from trade flow and monitor their positions."""

    def __init__(
        self,
        storage: StorageProtocol,
        reader: ExchangeReader,
        settings: HyperSussySettings,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._settings = settings
        self._whale_discovery = WhaleDiscovery(storage, settings)
        self._twap_detector = TwapDetector(settings)
        self._position_tracker = PositionTracker(
            storage, reader, settings, twap_detector=self._twap_detector
        )
        self._position_census: PositionCensus | None = (
            PositionCensus(storage, reader, settings)
            if settings.census_enabled
            else None
        )
        self._whale_active_dexes: dict[str, set[str]] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "whale_tracker"

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Accumulate per-address volume and promote whales.

        ``_whale_active_dexes`` is intentionally populated for *every*
        HIP-3 trader, not just tracked whales. When discovery later
        promotes an address, its accumulated dex profile is already
        available — the first REST position poll can target just the
        dexes the address has actually traded on, instead of
        fan-scanning every known HIP-3 dex. Pruning back to the
        tracked set happens once per ``tick()``.
        """
        await self._whale_discovery.on_trade(trade)
        if self._position_census is not None:
            await self._position_census.on_trade(trade)
        dex_prefix = trade.coin.split(":", 1)[0] if ":" in trade.coin else ""
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            if dex_prefix:
                self._whale_active_dexes.setdefault(addr, set()).add(dex_prefix)
        return []

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Track latest OI per coin for position/OI ratio."""
        self._whale_discovery.set_coin_oi(snapshot.coin, snapshot.open_interest_usd)
        self._position_tracker.set_coin_oi(snapshot.coin, snapshot.open_interest_usd)
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Prune volume window, poll whale positions, detect changes."""
        self._whale_discovery.prune_volume(timestamp_ms)
        self._whale_discovery.cap_tracked()

        db_tracked = set(await self._storage.get_tracked_addresses())
        merged = self._whale_discovery.get_tracked() | db_tracked
        self._whale_discovery.set_tracked(merged)

        # Only rebuild the dex filter if at least one tracked address
        # was demoted between ticks. ``keys() <= tracked`` is an O(N)
        # subset check on the dict's keyview against the tracked set,
        # cheap to do every tick and avoids allocating a new dict on
        # the common case where no whales got demoted.
        tracked = self._whale_discovery.get_tracked()
        if not (self._whale_active_dexes.keys() <= tracked):
            self._whale_active_dexes = {
                addr: dexes
                for addr, dexes in self._whale_active_dexes.items()
                if addr in tracked
            }
        self._position_tracker.set_whale_active_dexes(self._whale_active_dexes)

        alerts = await self._position_tracker.poll_positions(timestamp_ms, tracked)

        if self._position_census is not None:
            await self._position_census.tick(timestamp_ms, tracked)

        return alerts

    async def on_position_update(
        self,
        address: str,
        positions: list[Position],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Process a WebSocket-pushed position update for an address."""
        return await self._position_tracker.on_position_update(
            address, positions, timestamp_ms
        )
