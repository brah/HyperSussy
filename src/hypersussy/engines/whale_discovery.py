"""Passively discovers high-volume addresses from the trade stream."""

from __future__ import annotations

import logging
from collections import deque

from hypersussy.config import HyperSussySettings
from hypersussy.models import Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class WhaleDiscovery:
    """Discovers whales from trade flow."""

    def __init__(self, storage: StorageProtocol, settings: HyperSussySettings) -> None:
        self._storage = storage
        self._settings = settings
        self._address_volume: dict[str, float] = {}
        self._address_coin_volume: dict[tuple[str, str], float] = {}
        self._trade_buffer: deque[tuple[int, str, str, str, float]] = deque()
        self._tracked: set[str] = set()
        self._coin_oi: dict[str, float] = {}

    async def on_trade(self, trade: Trade) -> None:
        """Accumulate per-address volume and promote whales."""
        notional = trade.price * trade.size
        self._trade_buffer.append(
            (trade.timestamp_ms, trade.buyer, trade.seller, trade.coin, notional)
        )
        coin_oi = self._coin_oi.get(trade.coin, 0.0)
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            self._address_volume[addr] = self._address_volume.get(addr, 0.0) + notional
            key = (addr, trade.coin)
            self._address_coin_volume[key] = (
                self._address_coin_volume.get(key, 0.0) + notional
            )
            if addr in self._tracked:
                continue
            usd_ok = (
                self._address_volume[addr] >= self._settings.whale_volume_threshold_usd
            )
            oi_ok = (
                coin_oi > 0
                and self._address_coin_volume[key]
                >= self._settings.whale_discovery_oi_pct * coin_oi
                and self._address_coin_volume[key]
                >= self._settings.whale_oi_min_notional_usd
            )
            if usd_ok or oi_ok:
                label = f"{trade.coin} OI WHALE" if oi_ok else f"{trade.coin} WHALE"
                self._tracked.add(addr)
                await self._storage.upsert_tracked_address(
                    addr,
                    label,
                    "discovered",
                    self._address_volume[addr],
                )
                logger.info(
                    "Whale discovered: %s label=%s (volume=$%.0f)",
                    addr,
                    label,
                    self._address_volume[addr],
                )

    def prune_volume(self, timestamp_ms: int) -> None:
        """Remove expired entries from the sliding volume window."""
        cutoff = timestamp_ms - self._settings.whale_volume_lookback_ms
        while self._trade_buffer and self._trade_buffer[0][0] < cutoff:
            _, buyer, seller, coin, notional = self._trade_buffer.popleft()
            for addr in (buyer, seller):
                if not addr:
                    continue
                vol = self._address_volume.get(addr, 0.0) - notional
                if vol <= 0:
                    self._address_volume.pop(addr, None)
                else:
                    self._address_volume[addr] = vol
                ck = (addr, coin)
                cvol = self._address_coin_volume.get(ck, 0.0) - notional
                if cvol <= 0:
                    self._address_coin_volume.pop(ck, None)
                else:
                    self._address_coin_volume[ck] = cvol

    def cap_tracked(self) -> None:
        """Limit tracked addresses to max_tracked_addresses."""
        if len(self._tracked) <= self._settings.max_tracked_addresses:
            return
        sorted_addrs = sorted(
            self._tracked,
            key=lambda a: self._address_volume.get(a, 0.0),
            reverse=True,
        )
        self._tracked = set(sorted_addrs[: self._settings.max_tracked_addresses])

    def set_coin_oi(self, coin: str, oi: float) -> None:
        self._coin_oi[coin] = oi

    def get_tracked(self) -> set[str]:
        return self._tracked

    def set_tracked(self, tracked: set[str]) -> None:
        self._tracked = tracked
