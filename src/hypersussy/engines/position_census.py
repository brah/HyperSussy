"""Position census: polls positions for non-whale trade-stream addresses.

Broadens the "Top Positions" view beyond tracked whales by polling
any address with significant recent trading activity.  Uses a
sliding-window volume accumulator and interval-gated batch polling,
similar to PositionTracker but at a lower priority cadence.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from hypersussy.config import HyperSussySettings
from hypersussy.exchange.base import ExchangeReader
from hypersussy.exchange.hyperliquid.client import PositionFetchRateLimitError
from hypersussy.logging_utils import LogFloodGuard
from hypersussy.models import Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class PositionCensus:
    """Polls positions for non-whale addresses seen in the trade stream.

    Tracks per-address cumulative volume in a sliding window.  On each
    ``tick``, selects the highest-volume non-whale addresses that are
    due for a position refresh, fetches their positions (native dex
    only), and stores the results.  Does not generate alerts.

    Args:
        storage: Persistent storage for position snapshots.
        reader: Exchange reader for position queries.
        settings: Application settings with census thresholds.
    """

    def __init__(
        self,
        storage: StorageProtocol,
        reader: ExchangeReader,
        settings: HyperSussySettings,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._settings = settings
        self._address_volume: dict[str, float] = {}
        self._trade_buffer: deque[tuple[int, str, str, float]] = deque()
        self._last_polled: dict[str, float] = {}
        self._log_guard = LogFloodGuard(window_s=60.0)

    def on_trade(self, trade: Trade) -> None:
        """Accumulate per-address volume from the trade stream.

        Args:
            trade: Incoming trade with buyer/seller addresses.
        """
        notional = trade.price * trade.size
        self._trade_buffer.append(
            (trade.timestamp_ms, trade.buyer, trade.seller, notional)
        )
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            self._address_volume[addr] = self._address_volume.get(addr, 0.0) + notional

        if len(self._address_volume) > self._settings.census_max_addresses * 2:
            self._evict_lowest()

    def prune_volume(self, timestamp_ms: int) -> None:
        """Remove expired entries from the sliding volume window.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
        """
        cutoff = timestamp_ms - self._settings.census_volume_lookback_ms
        while self._trade_buffer and self._trade_buffer[0][0] < cutoff:
            _, buyer, seller, notional = self._trade_buffer.popleft()
            for addr in (buyer, seller):
                if not addr:
                    continue
                vol = self._address_volume.get(addr, 0.0) - notional
                if vol <= 0:
                    self._address_volume.pop(addr, None)
                else:
                    self._address_volume[addr] = vol

    async def tick(self, timestamp_ms: int, whale_addresses: set[str]) -> None:
        """Poll positions for a batch of non-whale addresses.

        Selects addresses by descending volume, excluding whales and
        those polled within ``census_poll_interval_s``.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
            whale_addresses: Tracked whale addresses to exclude.
        """
        self.prune_volume(timestamp_ms)

        now_s = timestamp_ms / 1000.0
        interval = self._settings.census_poll_interval_s

        candidates = [
            (addr, vol)
            for addr, vol in self._address_volume.items()
            if addr not in whale_addresses
            and vol >= self._settings.census_min_volume_usd
            and now_s - self._last_polled.get(addr, 0.0) >= interval
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)

        limit = self._settings.census_poll_batch_size
        batch = [addr for addr, _ in candidates[:limit]]
        if not batch:
            return

        results = await asyncio.gather(
            *(
                self._reader.get_user_positions(addr, active_dexes=set())
                for addr in batch
            ),
            return_exceptions=True,
        )

        for addr, result in zip(batch, results, strict=True):
            if isinstance(result, PositionFetchRateLimitError):
                self._log_guard.log(
                    logger,
                    logging.INFO,
                    f"position_census_429:{addr}",
                    (
                        "Census rate-limited for %s on %d dex(es); backing off"
                    ),
                    addr,
                    len(result.dexes),
                )
                self._last_polled[addr] = now_s
                continue
            if isinstance(result, BaseException):
                self._log_guard.log(
                    logger,
                    logging.INFO,
                    f"position_census_error:{addr}:{type(result).__name__}",
                    "Census failed for %s (%s)",
                    addr,
                    result,
                )
                continue

            positions = result
            self._last_polled[addr] = now_s

            if positions:
                await self._storage.insert_positions(positions)

    def _evict_lowest(self) -> None:
        """Evict lowest-volume addresses to stay within memory cap."""
        if len(self._address_volume) <= self._settings.census_max_addresses:
            return
        sorted_addrs = sorted(
            self._address_volume,
            key=self._address_volume.__getitem__,
            reverse=True,
        )
        keep = set(sorted_addrs[: self._settings.census_max_addresses])
        self._address_volume = {
            a: v for a, v in self._address_volume.items() if a in keep
        }
