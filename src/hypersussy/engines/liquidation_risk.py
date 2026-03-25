"""Liquidation cascade risk detection engine.

Monitors tracked whale positions approaching liquidation and
estimates potential market impact by cross-referencing order
book depth.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.config import HyperSussySettings
from hypersussy.exchange.base import ExchangeReader
from hypersussy.models import Alert, AssetSnapshot, L2Book, Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


class LiquidationRiskEngine:
    """Detect whales approaching liquidation with market impact.

    Args:
        storage: Storage backend for tracked addresses and positions.
        reader: Exchange reader for L2 book snapshots.
        settings: Application settings with risk thresholds.
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
        # Cache latest mark prices from asset updates
        self._mark_prices: dict[str, float] = {}
        # Cooldown: key -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "liquidation_risk"

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """No-op for this engine.

        Args:
            trade: The incoming trade.

        Returns:
            Empty list.
        """
        return []

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Cache latest mark prices.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        self._mark_prices[snapshot.coin] = snapshot.mark_price
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Check tracked whales for liquidation proximity.

        Caches L2 book fetches per coin so each book is retrieved at
        most once per tick regardless of how many whales hold that coin.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for whales near liquidation with impact risk.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        threshold = self._settings.liquidation_distance_threshold
        book_cache: dict[str, L2Book | None] = {}

        tracked = await self._storage.get_tracked_addresses()

        for address in tracked[:50]:
            try:
                positions = await self._storage.get_latest_positions(address)
            except sqlite3.Error:
                logger.exception("Failed to get positions for %s", address)
                continue

            for pos in positions:
                if pos.liquidation_price is None or pos.liquidation_price == 0:
                    continue

                mark = self._mark_prices.get(pos.coin, pos.mark_price)
                if mark == 0:
                    continue

                distance = abs(mark - pos.liquidation_price) / mark
                if distance >= threshold:
                    continue

                key = f"{address}:{pos.coin}"
                if timestamp_ms - self._last_alert_ms.get(key, 0) < cooldown_ms:
                    continue

                impact_ratio = await self._estimate_impact(
                    pos.coin, abs(pos.size), book_cache
                )

                alerts.append(
                    _liquidation_alert(
                        _LiquidationContext(
                            address=address,
                            coin=pos.coin,
                            size=pos.size,
                            notional_usd=pos.notional_usd,
                            mark_price=mark,
                            liq_price=pos.liquidation_price,
                            distance=distance,
                            impact_ratio=impact_ratio,
                            timestamp_ms=timestamp_ms,
                        )
                    )
                )
                self._last_alert_ms[key] = timestamp_ms

        return alerts

    async def _estimate_impact(
        self,
        coin: str,
        position_size: float,
        book_cache: dict[str, L2Book | None],
    ) -> float:
        """Estimate market impact of liquidating a position.

        Uses *book_cache* to avoid fetching the same coin's L2 book
        multiple times within a single tick.

        Args:
            coin: Asset name.
            position_size: Absolute position size.
            book_cache: Mutable cache of coin -> L2Book for this tick.

        Returns:
            Ratio of position size to available book depth.
            Higher values indicate more impact risk.
        """
        if coin not in book_cache:
            try:
                book_cache[coin] = await self._reader.get_l2_book(coin)
            except (ClientError, ServerError, requests.RequestException, OSError):
                logger.warning("Failed to fetch L2 book for %s", coin)
                book_cache[coin] = None  # sentinel to avoid retrying
        book = book_cache[coin]
        if book is None:
            return 0.0
        return _compute_impact_ratio(book, position_size)


def _compute_impact_ratio(book: L2Book, position_size: float) -> float:
    """Compute ratio of position size to nearby book depth.

    Args:
        book: Order book snapshot.
        position_size: Absolute position size to liquidate.

    Returns:
        Impact ratio (position / book_depth).
    """
    total_depth = sum(size for _, size in book.bids) + sum(
        size for _, size in book.asks
    )
    if total_depth == 0:
        return float("inf")
    return position_size / total_depth


def _classify_severity(distance: float, impact_ratio: float) -> str:
    """Classify alert severity from liquidation distance and impact.

    Args:
        distance: Distance to liquidation as fraction of mark price.
        impact_ratio: Position size / book depth ratio.

    Returns:
        Severity string.
    """
    if distance < 0.02 and impact_ratio > 0.5:
        return "critical"
    if distance < 0.03 or impact_ratio > 0.3:
        return "high"
    if distance < 0.05:
        return "medium"
    return "low"


@dataclass(frozen=True, slots=True)
class _LiquidationContext:
    """Data needed to generate a liquidation risk alert."""

    address: str
    coin: str
    size: float
    notional_usd: float
    mark_price: float
    liq_price: float
    distance: float
    impact_ratio: float
    timestamp_ms: int


def _liquidation_alert(ctx: _LiquidationContext) -> Alert:
    """Create a liquidation risk alert.

    Args:
        ctx: Bundled liquidation context data.

    Returns:
        A liquidation_risk alert.
    """
    side = "long" if ctx.size > 0 else "short"
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="liquidation_risk",
        severity=_classify_severity(ctx.distance, ctx.impact_ratio),
        coin=ctx.coin,
        title=(f"{ctx.coin}: whale {side} {ctx.distance:.1%} from liquidation"),
        description=(
            f"Address {ctx.address[:10]}... holds a "
            f"${abs(ctx.notional_usd):,.0f} "
            f"{side} on {ctx.coin}. Mark={ctx.mark_price:.2f}, "
            f"liq={ctx.liq_price:.2f} ({ctx.distance:.1%} away). "
            f"Impact ratio={ctx.impact_ratio:.2f}."
        ),
        timestamp_ms=ctx.timestamp_ms,
        metadata={
            "address": ctx.address,
            "size": ctx.size,
            "notional_usd": ctx.notional_usd,
            "mark_price": ctx.mark_price,
            "liquidation_price": ctx.liq_price,
            "distance": ctx.distance,
            "impact_ratio": ctx.impact_ratio,
        },
    )
