"""Passively discovers high-volume addresses from the trade stream."""

from __future__ import annotations

import logging

from hypersussy.config import HyperSussySettings
from hypersussy.engines._volume_window import SlidingVolumeWindow
from hypersussy.models import Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class WhaleDiscovery:
    """Discovers whales from trade flow.

    Promotes an address once its rolling volume in the last
    ``whale_volume_lookback_ms`` crosses ``whale_volume_threshold_usd``,
    or once its volume on a single coin crosses
    ``whale_discovery_oi_pct`` of that coin's open interest (with a
    minimum notional floor).
    """

    def __init__(self, storage: StorageProtocol, settings: HyperSussySettings) -> None:
        self._storage = storage
        self._settings = settings
        self._window = SlidingVolumeWindow(track_coin_volume=True)
        self._tracked: set[str] = set()
        self._coin_oi: dict[str, float] = {}

    async def on_trade(self, trade: Trade) -> None:
        """Accumulate per-address volume and promote whales."""
        notional = trade.price * trade.size
        self._window.add_trade(
            trade.timestamp_ms, trade.buyer, trade.seller, trade.coin, notional
        )
        coin_oi = self._coin_oi.get(trade.coin, 0.0)
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            if addr in self._tracked:
                continue
            addr_volume = self._window.address_volume.get(addr, 0.0)
            coin_volume = self._window.coin_address_volume.get((addr, trade.coin), 0.0)
            usd_ok = addr_volume >= self._settings.whale_volume_threshold_usd
            oi_ok = (
                coin_oi > 0
                and coin_volume >= self._settings.whale_discovery_oi_pct * coin_oi
                and coin_volume >= self._settings.whale_oi_min_notional_usd
            )
            if usd_ok or oi_ok:
                label = f"{trade.coin} OI WHALE" if oi_ok else f"{trade.coin} WHALE"
                self._tracked.add(addr)
                await self._storage.upsert_tracked_address(
                    addr,
                    label,
                    "discovered",
                    addr_volume,
                )
                logger.info(
                    "Whale discovered: %s label=%s (volume=$%.0f)",
                    addr,
                    label,
                    addr_volume,
                )

    def prune_volume(self, timestamp_ms: int) -> None:
        """Remove expired entries from the sliding volume window."""
        self._window.prune(timestamp_ms, self._settings.whale_volume_lookback_ms)

    def cap_tracked(self) -> None:
        """Limit tracked addresses to max_tracked_addresses."""
        if len(self._tracked) <= self._settings.max_tracked_addresses:
            return
        sorted_addrs = sorted(
            self._tracked,
            key=lambda a: self._window.address_volume.get(a, 0.0),
            reverse=True,
        )
        self._tracked = set(sorted_addrs[: self._settings.max_tracked_addresses])

    def set_coin_oi(self, coin: str, oi: float) -> None:
        self._coin_oi[coin] = oi

    def get_tracked(self) -> set[str]:
        return self._tracked

    def set_tracked(self, tracked: set[str]) -> None:
        self._tracked = tracked
