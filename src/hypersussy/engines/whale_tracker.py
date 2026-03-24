"""Whale discovery and position tracking engine.

Passively discovers high-volume addresses from the trade stream,
promotes them to a tracked list, and periodically polls their
positions to detect large or changing holdings.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque

from hypersussy.config import HyperSussySettings
from hypersussy.exchange.base import ExchangeReader
from hypersussy.models import Alert, AssetSnapshot, Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class WhaleTrackerEngine:
    """Discover whales from trade flow and monitor their positions.

    Args:
        storage: Storage backend for persistence.
        reader: Exchange reader for position polling.
        settings: Application settings with thresholds.
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
        # Sliding-window volume tracking
        self._address_volume: dict[str, float] = {}
        self._trade_buffer: deque[tuple[int, str, str, float]] = deque()
        # Tracked whales
        self._tracked: set[str] = set()
        # Last known positions per address
        self._last_positions: dict[str, list[tuple[str, float]]] = {}
        # Last poll time per address (seconds)
        self._last_polled: dict[str, float] = {}
        # Latest OI per coin for position/OI ratio
        self._coin_oi: dict[str, float] = {}
        # Cooldown: key -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "whale_tracker"

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Accumulate per-address volume and promote whales.

        Args:
            trade: The incoming trade.

        Returns:
            Empty list (alerts generated in tick).
        """
        notional = trade.price * trade.size
        self._trade_buffer.append(
            (trade.timestamp_ms, trade.buyer, trade.seller, notional)
        )
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            self._address_volume[addr] = self._address_volume.get(addr, 0.0) + notional
            if (
                addr not in self._tracked
                and self._address_volume[addr]
                >= self._settings.whale_volume_threshold_usd
            ):
                self._tracked.add(addr)
                await self._storage.upsert_tracked_address(
                    addr,
                    f"{trade.coin} WHALE",
                    "discovered",
                    self._address_volume[addr],
                )
                logger.info(
                    "Whale discovered: %s (volume=$%.0f)",
                    addr,
                    self._address_volume[addr],
                )
        return []

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Track latest OI per coin for position/OI ratio.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        self._coin_oi[snapshot.coin] = snapshot.open_interest_usd
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Prune volume window, poll whale positions, detect changes.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for large positions or significant changes.
        """
        self._prune_volume(timestamp_ms)
        self._cap_tracked()
        return await self._poll_positions(timestamp_ms)

    def _prune_volume(self, timestamp_ms: int) -> None:
        """Remove expired entries from the sliding volume window.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
        """
        cutoff = timestamp_ms - self._settings.whale_volume_lookback_ms
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

    def _cap_tracked(self) -> None:
        """Limit tracked addresses to max_tracked_addresses."""
        if len(self._tracked) <= self._settings.max_tracked_addresses:
            return
        sorted_addrs = sorted(
            self._tracked,
            key=lambda a: self._address_volume.get(a, 0.0),
            reverse=True,
        )
        self._tracked = set(sorted_addrs[: self._settings.max_tracked_addresses])

    async def _poll_positions(self, timestamp_ms: int) -> list[Alert]:
        """Poll positions for tracked whales due for refresh.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for notable position changes.
        """
        alerts: list[Alert] = []
        now_s = timestamp_ms / 1000.0
        cooldown_ms = self._settings.alert_cooldown_s * 1000

        to_poll = [
            addr
            for addr in self._tracked
            if now_s - self._last_polled.get(addr, 0.0)
            >= self._settings.position_poll_interval_s
        ]

        for addr in to_poll[:10]:
            try:
                positions = await self._reader.get_user_positions(addr)
                self._last_polled[addr] = now_s

                if positions:
                    await self._storage.insert_positions(positions)

                current = {p.coin: p.notional_usd for p in positions}
                prev = dict(self._last_positions.get(addr, []))

                for pos in positions:
                    # Check position / OI ratio
                    coin_oi = self._coin_oi.get(pos.coin, 0.0)
                    if coin_oi > 0:
                        oi_pct = abs(pos.notional_usd) / coin_oi
                        if oi_pct >= self._settings.large_position_oi_pct:
                            key = f"{addr}:{pos.coin}"
                            if (
                                timestamp_ms - self._last_alert_ms.get(key, 0)
                                >= cooldown_ms
                            ):
                                alerts.append(
                                    _position_alert(
                                        addr,
                                        pos.coin,
                                        pos.notional_usd,
                                        oi_pct,
                                        timestamp_ms,
                                    )
                                )
                                self._last_alert_ms[key] = timestamp_ms

                    # Check position size change
                    prev_notional = prev.get(pos.coin, 0.0)
                    change_usd = abs(pos.notional_usd - prev_notional)
                    if change_usd >= self._settings.large_position_change_usd:
                        key = f"{addr}:{pos.coin}:change"
                        if (
                            timestamp_ms - self._last_alert_ms.get(key, 0)
                            >= cooldown_ms
                        ):
                            alerts.append(
                                _change_alert(
                                    addr,
                                    pos.coin,
                                    prev_notional,
                                    pos.notional_usd,
                                    change_usd,
                                    timestamp_ms,
                                )
                            )
                            self._last_alert_ms[key] = timestamp_ms

                self._last_positions[addr] = list(current.items())
            except Exception:
                logger.exception("Failed to poll positions for %s", addr)

        return alerts


def _position_alert(
    address: str,
    coin: str,
    notional_usd: float,
    oi_pct: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for a large position relative to OI.

    Args:
        address: Whale address.
        coin: Asset name.
        notional_usd: Position notional value.
        oi_pct: Position as fraction of total OI.
        timestamp_ms: Alert timestamp.

    Returns:
        A whale_position alert.
    """
    severity = "critical" if oi_pct > 0.15 else "high" if oi_pct > 0.10 else "medium"
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="whale_position",
        severity=severity,
        coin=coin,
        title=f"{coin}: whale holds {oi_pct:.1%} of OI",
        description=(
            f"Address {address[:10]}... holds ${abs(notional_usd):,.0f} "
            f"notional ({oi_pct:.1%} of open interest) on {coin}."
        ),
        timestamp_ms=timestamp_ms,
        metadata={
            "address": address,
            "notional_usd": notional_usd,
            "oi_pct": oi_pct,
        },
    )


def _change_alert(
    address: str,
    coin: str,
    prev_notional: float,
    current_notional: float,
    change_usd: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for a significant position change.

    Args:
        address: Whale address.
        coin: Asset name.
        prev_notional: Previous position notional.
        current_notional: Current position notional.
        change_usd: Absolute change in USD.
        timestamp_ms: Alert timestamp.

    Returns:
        A whale_position_change alert.
    """
    direction = "increased" if current_notional > prev_notional else "decreased"
    severity = "high" if change_usd > 5_000_000 else "medium"
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="whale_position_change",
        severity=severity,
        coin=coin,
        title=f"{coin}: whale position {direction} by ${change_usd:,.0f}",
        description=(
            f"Address {address[:10]}... {direction} {coin} position "
            f"from ${prev_notional:,.0f} to ${current_notional:,.0f} "
            f"(${change_usd:,.0f} change)."
        ),
        timestamp_ms=timestamp_ms,
        metadata={
            "address": address,
            "prev_notional_usd": prev_notional,
            "current_notional_usd": current_notional,
            "change_usd": change_usd,
        },
    )
