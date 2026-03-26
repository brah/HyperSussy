"""Whale discovery and position tracking engine.

Passively discovers high-volume addresses from the trade stream,
promotes them to a tracked list, and periodically polls their
positions to detect large or changing holdings.
"""

from __future__ import annotations

import asyncio
import logging

from hypersussy.config import HyperSussySettings
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
        self._position_tracker = PositionTracker(storage, reader, settings)
        self._twap_detector = TwapDetector(settings)
        self._whale_active_dexes: dict[str, set[str]] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "whale_tracker"

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Accumulate per-address volume and promote whales."""
        await self._whale_discovery.on_trade(trade)
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
        self._whale_discovery.set_tracked(self._whale_discovery.get_tracked() | db_tracked)
        
        self._whale_active_dexes = {
            addr: dexes
            for addr, dexes in self._whale_active_dexes.items()
            if addr in self._whale_discovery.get_tracked()
        }
        self._position_tracker.set_whale_active_dexes(self._whale_active_dexes)

        position_alerts = await self._position_tracker.poll_positions(
            timestamp_ms, self._whale_discovery.get_tracked()
        )

        # This part is tricky. The original implementation fetched twap_fills during position polling.
        # To keep concerns separate, we would ideally fetch them separately.
        # However, to minimize API calls, we can fetch them together.
        # For now, we will do a separate fetch, but this could be optimized.
        twap_alerts = []
        for addr in self._whale_discovery.get_tracked():
            try:
                twap_fills = await self._reader.get_user_twap_slice_fills(addr)
                twap_alerts.extend(
                    self._twap_detector.process_twap_fills(addr, twap_fills, timestamp_ms)
                )
            except Exception:
                logger.exception("Failed to get TWAP fills for %s", addr)

        return position_alerts + twap_alerts

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
