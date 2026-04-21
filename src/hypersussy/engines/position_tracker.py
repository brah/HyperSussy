"""Polls positions of tracked whales and generates alerts."""

from __future__ import annotations

import asyncio
import logging
import uuid

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import (
    classify_severity,
    is_on_cooldown,
    record_alert_timestamp,
)
from hypersussy.engines.twap_detector import TwapDetector
from hypersussy.exchange.base import ExchangeReader
from hypersussy.exchange.hyperliquid.client import PositionFetchRateLimitError
from hypersussy.logging_utils import LogFloodGuard
from hypersussy.models import Alert, Position, TwapSliceFill
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)

# Score = oi_pct (fraction of OI represented by the position).
_POSITION_OI_SEVERITY_CUTOFFS = (
    (0.15, "critical"),
    (0.10, "high"),
)

# Score = absolute change in USD between consecutive position snapshots.
_POSITION_CHANGE_SEVERITY_CUTOFFS = ((5_000_000.0, "high"),)


class PositionTracker:
    """Polls positions for tracked whales and detects changes."""

    def __init__(
        self,
        storage: StorageProtocol,
        reader: ExchangeReader,
        settings: HyperSussySettings,
        twap_detector: TwapDetector | None = None,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._settings = settings
        self._twap_detector = twap_detector
        # address -> coin -> last seen notional. Stored directly as a
        # nested dict so _generate_position_alerts() can do an O(1)
        # lookup per position instead of rebuilding a temporary dict
        # from a list-of-tuples on every call.
        self._last_positions: dict[str, dict[str, float]] = {}
        self._polled_once: set[str] = set()
        self._last_polled: dict[str, float] = {}
        self._coin_oi: dict[str, float] = {}
        self._whale_active_dexes: dict[str, set[str]] = {}
        self._last_alert_ms: dict[str, int] = {}
        self._log_guard = LogFloodGuard(window_s=60.0)

    async def poll_positions(
        self, timestamp_ms: int, db_tracked: set[str]
    ) -> list[Alert]:
        """Poll positions (and TWAP fills) for tracked whales due for refresh.

        TWAP fetching is piggybacked on the same batch/interval to avoid
        the O(N) per-tick cost of polling every tracked address separately.

        Args:
            timestamp_ms: Current timestamp in milliseconds.
            db_tracked: Set of tracked whale addresses.

        Returns:
            Combined position and TWAP alerts.
        """
        now_s = timestamp_ms / 1000.0

        to_poll = [
            addr
            for addr in db_tracked
            if now_s - self._last_polled.get(addr, 0.0)
            >= self._settings.position_poll_interval_s
        ]

        batch = to_poll[: self._settings.whale_poll_batch_size]
        if not batch:
            return []

        results = await asyncio.gather(
            *(self._fetch_addr_data(addr) for addr in batch),
            return_exceptions=True,
        )

        alerts: list[Alert] = []
        for addr, result in zip(batch, results, strict=True):
            if isinstance(result, PositionFetchRateLimitError):
                self._log_guard.log(
                    logger,
                    logging.WARNING,
                    f"position_tracker_429:{addr}",
                    (
                        "Rate-limited polling positions for %s on %d dex(es); "
                        "backing off"
                    ),
                    addr,
                    len(result.dexes),
                )
                self._last_polled[addr] = now_s
                continue
            if isinstance(result, BaseException):
                self._log_guard.log(
                    logger,
                    logging.WARNING,
                    f"position_tracker_error:{addr}:{type(result).__name__}",
                    "Failed to poll positions for %s (%s)",
                    addr,
                    result,
                )
                continue

            positions, twap_fills = result
            self._last_polled[addr] = now_s

            if positions:
                await self._storage.insert_positions(positions)

            pos_alerts = self._generate_position_alerts(addr, positions, timestamp_ms)
            alerts.extend(pos_alerts)

            if self._twap_detector and twap_fills:
                alerts.extend(
                    self._twap_detector.process_twap_fills(
                        addr, twap_fills, timestamp_ms
                    )
                )

            self._last_positions[addr] = {p.coin: p.notional_usd for p in positions}
            self._polled_once.add(addr)

        return alerts

    async def on_position_update(
        self,
        address: str,
        positions: list[Position],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Process a WebSocket-pushed position update for an address.

        Does *not* update ``_last_polled``: the REST safety net runs
        on its own cadence so a silently-stalled WS stream cannot
        suppress polling for tracked whales.
        """
        if positions:
            await self._storage.insert_positions(positions)

        alerts = self._generate_position_alerts(address, positions, timestamp_ms)
        self._last_positions[address] = {p.coin: p.notional_usd for p in positions}
        self._polled_once.add(address)
        return alerts

    def _generate_position_alerts(
        self,
        address: str,
        positions: list[Position],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Generate large-position and change alerts from a position list."""
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        prev = self._last_positions.get(address, {})
        alerts: list[Alert] = []

        for pos in positions:
            coin_oi = self._coin_oi.get(pos.coin, 0.0)
            if coin_oi > 0 and coin_oi >= self._settings.large_position_min_oi_usd:
                oi_pct = abs(pos.notional_usd) / coin_oi
                if oi_pct >= self._settings.large_position_oi_pct:
                    key = f"{address}:{pos.coin}"
                    if not is_on_cooldown(
                        self._last_alert_ms, key, timestamp_ms, cooldown_ms
                    ):
                        alerts.append(
                            _position_alert(
                                address,
                                pos.coin,
                                pos.notional_usd,
                                oi_pct,
                                timestamp_ms,
                            )
                        )
                        record_alert_timestamp(self._last_alert_ms, key, timestamp_ms)

            if address in self._polled_once:
                prev_notional = prev.get(pos.coin, 0.0)
                change_usd = abs(pos.notional_usd - prev_notional)
                if change_usd >= self._settings.large_position_change_usd:
                    key = f"{address}:{pos.coin}:change"
                    if not is_on_cooldown(
                        self._last_alert_ms, key, timestamp_ms, cooldown_ms
                    ):
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
                        record_alert_timestamp(self._last_alert_ms, key, timestamp_ms)

        return alerts

    async def _fetch_addr_data(
        self, addr: str
    ) -> tuple[list[Position], list[TwapSliceFill]]:
        """Fetch positions and TWAP fills for an address concurrently.

        Args:
            addr: The 0x wallet address.

        Returns:
            Tuple of (positions, twap_fills).
        """
        pos_coro = self._reader.get_user_positions(
            addr,
            active_dexes=self._whale_active_dexes.get(addr),
        )
        if self._twap_detector is not None:
            twap_coro = self._reader.get_user_twap_slice_fills(addr)
            positions, twap_fills = await asyncio.gather(
                pos_coro, twap_coro, return_exceptions=False
            )
            return positions, twap_fills
        return await pos_coro, []

    def set_coin_oi(self, coin: str, oi: float) -> None:
        self._coin_oi[coin] = oi

    def set_whale_active_dexes(self, whale_active_dexes: dict[str, set[str]]) -> None:
        self._whale_active_dexes = whale_active_dexes


def _position_alert(
    address: str,
    coin: str,
    notional_usd: float,
    oi_pct: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for a large position relative to OI."""
    severity = classify_severity(
        oi_pct, _POSITION_OI_SEVERITY_CUTOFFS, default="medium"
    )
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
    """Create an alert for a significant position change."""
    direction = "increased" if current_notional > prev_notional else "decreased"
    severity = classify_severity(
        change_usd, _POSITION_CHANGE_SEVERITY_CUTOFFS, default="medium"
    )
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
