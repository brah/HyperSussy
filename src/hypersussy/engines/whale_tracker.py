"""Whale discovery and position tracking engine.

Passively discovers high-volume addresses from the trade stream,
promotes them to a tracked list, and periodically polls their
positions to detect large or changing holdings.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque

from hyperliquid.utils.error import ClientError

from hypersussy.config import HyperSussySettings
from hypersussy.exchange.base import ExchangeReader
from hypersussy.models import (
    Alert,
    AssetSnapshot,
    Position,
    Trade,
    TwapFillEntry,
    TwapSliceFill,
)
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
        # Sliding-window volume tracking (global and per-coin)
        self._address_volume: dict[str, float] = {}
        self._address_coin_volume: dict[tuple[str, str], float] = {}
        self._trade_buffer: deque[tuple[int, str, str, str, float]] = deque()
        # Tracked whales
        self._tracked: set[str] = set()
        # Last known positions per address
        self._last_positions: dict[str, list[tuple[str, float]]] = {}
        # Addresses that have completed at least one full position poll
        self._polled_once: set[str] = set()
        # Last poll time per address (seconds)
        self._last_polled: dict[str, float] = {}
        # Latest OI per coin for position/OI ratio
        self._coin_oi: dict[str, float] = {}
        # HIP-3 dex prefixes observed per address in the trade stream.
        # Used to restrict position polling to relevant dexes only.
        self._whale_active_dexes: dict[str, set[str]] = {}
        # Cooldown: key -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}
        # Last seen TWAP fill tid per (address, twapId) to avoid re-alerting
        self._seen_twap_tids: dict[str, set[int]] = {}

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
            (trade.timestamp_ms, trade.buyer, trade.seller, trade.coin, notional)
        )
        coin_oi = self._coin_oi.get(trade.coin, 0.0)
        dex_prefix = trade.coin.split(":", 1)[0] if ":" in trade.coin else ""
        for addr in (trade.buyer, trade.seller):
            if not addr:
                continue
            if dex_prefix:
                self._whale_active_dexes.setdefault(addr, set()).add(dex_prefix)
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
        return []

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:  # noqa: RUF029
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

        Syncs the in-memory tracked set with the database each tick so
        that manual additions and UI removals take effect promptly.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for large positions or significant changes.
        """
        self._prune_volume(timestamp_ms)
        self._cap_tracked()
        # Sync with DB: pick up manual adds, respect UI removals
        db_tracked = set(await self._storage.get_tracked_addresses())
        self._tracked = self._tracked | db_tracked
        # Bound _whale_active_dexes to the current tracked set so untracked
        # addresses discovered in the trade stream don't accumulate forever.
        self._whale_active_dexes = {
            addr: dexes
            for addr, dexes in self._whale_active_dexes.items()
            if addr in self._tracked
        }
        return await self._poll_positions(timestamp_ms, db_tracked)

    def _prune_volume(self, timestamp_ms: int) -> None:
        """Remove expired entries from the sliding volume window.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
        """
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

    async def _poll_positions(
        self, timestamp_ms: int, db_tracked: set[str]
    ) -> list[Alert]:
        """Poll positions for tracked whales due for refresh.

        Fetches positions and TWAP fills concurrently across up to 10
        addresses using ``asyncio.gather``, then processes results
        sequentially to update shared state.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
            db_tracked: Addresses currently in the database.

        Returns:
            Alerts for notable position changes.
        """
        now_s = timestamp_ms / 1000.0
        cooldown_ms = self._settings.alert_cooldown_s * 1000

        to_poll = [
            addr
            for addr in db_tracked
            if now_s - self._last_polled.get(addr, 0.0)
            >= self._settings.position_poll_interval_s
        ]

        batch = to_poll[:10]
        if not batch:
            return []

        # Fetch positions + TWAP fills concurrently
        results = await asyncio.gather(
            *(self._fetch_addr_data(addr) for addr in batch),
            return_exceptions=True,
        )

        alerts: list[Alert] = []
        for addr, result in zip(batch, results, strict=True):
            if isinstance(result, ClientError):
                if result.status_code == 429:
                    logger.warning(
                        "Rate-limited polling positions for %s — backing off", addr
                    )
                    self._last_polled[addr] = now_s
                else:
                    logger.exception("Client error polling positions for %s", addr)
                continue
            if isinstance(result, BaseException):
                logger.exception("Failed to poll positions for %s", addr)
                continue

            positions, twap_fills = result
            self._last_polled[addr] = now_s

            if positions:
                await self._storage.insert_positions(positions)

            pos_alerts = self._generate_position_alerts(addr, positions, timestamp_ms)
            alerts.extend(pos_alerts)

            self._last_positions[addr] = [(p.coin, p.notional_usd) for p in positions]
            self._polled_once.add(addr)

            twap_alerts = self._process_twap_fills(
                addr, twap_fills, timestamp_ms, cooldown_ms
            )
            alerts.extend(twap_alerts)

        return alerts

    async def on_position_update(
        self,
        address: str,
        positions: list[Position],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Process a WebSocket-pushed position update for an address.

        Generates the same large-position and change-detection alerts as
        the REST polling path, without touching ``_last_polled`` so the
        safety-net poll cadence remains independent.

        Args:
            address: Whale address that received the update.
            positions: Current open positions from the WS push.
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for notable position states or changes.
        """
        if positions:
            await self._storage.insert_positions(positions)

        alerts = self._generate_position_alerts(address, positions, timestamp_ms)
        self._last_positions[address] = [(p.coin, p.notional_usd) for p in positions]
        self._polled_once.add(address)
        return alerts

    def _generate_position_alerts(
        self,
        address: str,
        positions: list[Position],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Generate large-position and change alerts from a position list.

        Shared by both the REST poll path and the WS push path.

        Args:
            address: Whale address.
            positions: Current open positions.
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Generated alerts.
        """
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        prev = dict(self._last_positions.get(address, []))
        alerts: list[Alert] = []

        for pos in positions:
            coin_oi = self._coin_oi.get(pos.coin, 0.0)
            if coin_oi >= self._settings.large_position_min_oi_usd:
                oi_pct = abs(pos.notional_usd) / coin_oi
                if oi_pct >= self._settings.large_position_oi_pct:
                    key = f"{address}:{pos.coin}"
                    if timestamp_ms - self._last_alert_ms.get(key, 0) >= cooldown_ms:
                        alerts.append(
                            _position_alert(
                                address,
                                pos.coin,
                                pos.notional_usd,
                                oi_pct,
                                timestamp_ms,
                            )
                        )
                        self._last_alert_ms[key] = timestamp_ms

            if address in self._polled_once:
                prev_notional = prev.get(pos.coin, 0.0)
                change_usd = abs(pos.notional_usd - prev_notional)
                if change_usd >= self._settings.large_position_change_usd:
                    key = f"{address}:{pos.coin}:change"
                    if timestamp_ms - self._last_alert_ms.get(key, 0) >= cooldown_ms:
                        alerts.append(
                            _change_alert(
                                address,
                                pos.coin,
                                prev_notional,
                                pos.notional_usd,
                                change_usd,
                                timestamp_ms,
                            )
                        )
                        self._last_alert_ms[key] = timestamp_ms

        return alerts

    async def _fetch_addr_data(
        self, addr: str
    ) -> tuple[list[Position], list[TwapSliceFill]]:
        """Fetch positions and TWAP fills for an address concurrently.

        Args:
            addr: Tracked whale address.

        Returns:
            Tuple of (positions, twap_fills).
        """
        positions, twap_fills = await asyncio.gather(
            self._reader.get_user_positions(
                addr,
                active_dexes=self._whale_active_dexes.get(addr),
            ),
            self._reader.get_user_twap_slice_fills(addr),
        )
        return positions, twap_fills

    def _process_twap_fills(
        self,
        addr: str,
        fills: list[TwapSliceFill],
        timestamp_ms: int,
        cooldown_ms: int,
    ) -> list[Alert]:
        """Process pre-fetched TWAP slice fills into alerts.

        Groups fills by twapId and alerts on any TWAP whose most
        recent fill is within the active window.

        Args:
            addr: Tracked whale address.
            fills: Raw TWAP slice fill entries from the API.
            timestamp_ms: Current timestamp in milliseconds.
            cooldown_ms: Alert cooldown in milliseconds.

        Returns:
            Alerts for each newly detected active TWAP.
        """
        if not fills:
            return []

        # Group by twapId, keeping only the latest fill per TWAP
        twap_latest: dict[int, TwapFillEntry] = {}
        for entry in fills:
            twap_id = entry["twapId"]
            fill = entry["fill"]
            fill_time = fill["time"]
            prev = twap_latest.get(twap_id)
            if prev is None or fill_time > prev["time"]:
                twap_latest[twap_id] = fill

        alerts: list[Alert] = []
        active_window_ms = int(self._settings.position_poll_interval_s * 1000) * 3

        for twap_id, latest_fill in twap_latest.items():
            fill_time = latest_fill["time"]
            if timestamp_ms - fill_time > active_window_ms:
                continue

            key = f"{addr}:twap:{twap_id}"
            if timestamp_ms - self._last_alert_ms.get(key, 0) < cooldown_ms:
                continue

            coin = latest_fill["coin"]
            is_buy = latest_fill["side"] == "B"
            sz = float(latest_fill["sz"])
            px = float(latest_fill["px"])

            alerts.append(
                _twap_active_alert(
                    addr,
                    coin,
                    twap_id,
                    "buy" if is_buy else "sell",
                    sz,
                    px,
                    timestamp_ms,
                )
            )
            self._last_alert_ms[key] = timestamp_ms

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
    if oi_pct > 0.15:
        severity = "critical"
    elif oi_pct > 0.10:
        severity = "high"
    else:
        severity = "medium"
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="whale_position",
        severity=severity,
        coin=coin,
        title=f"{coin}: whale holds {oi_pct:.1%} of OI (${abs(notional_usd):,.0f})",
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


def _twap_active_alert(
    address: str,
    coin: str,
    twap_id: int,
    direction: str,
    slice_sz: float,
    slice_px: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for a confirmed active TWAP execution.

    Args:
        address: Whale address executing the TWAP.
        coin: Asset name.
        twap_id: HyperLiquid TWAP order ID.
        direction: "buy" or "sell".
        slice_sz: Size of the most recent TWAP slice fill.
        slice_px: Price of the most recent TWAP slice fill.
        timestamp_ms: Alert timestamp.

    Returns:
        A twap_detected alert backed by HL API data.
    """
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="twap_detected",
        severity="medium",
        coin=coin,
        title=f"{coin}: active TWAP {direction} detected (id={twap_id})",
        description=(
            f"Address {address[:10]}... is executing a TWAP {direction} on {coin}. "
            f"Latest slice: {slice_sz:.4f} @ ${slice_px:,.4f} (twapId={twap_id})."
        ),
        timestamp_ms=timestamp_ms,
        metadata={
            "address": address,
            "twap_id": float(twap_id),
            "direction": direction,
            "slice_sz": slice_sz,
            "slice_px": slice_px,
        },
    )
