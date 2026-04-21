"""Liquidation cascade risk detection engine.

Monitors tracked whale positions approaching liquidation and
estimates potential market impact by cross-referencing order
book depth.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from dataclasses import dataclass

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.exchange.base import ExchangeReader
from hypersussy.models import Alert, AssetSnapshot, L2Book, Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)

_L2_FETCH_ERRORS = (ClientError, ServerError, requests.RequestException, OSError)


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

        Two passes so book fetches can run concurrently:

        1. Score all tracked positions against the distance threshold
           to collect the distinct set of coins that need an L2 book.
        2. ``asyncio.gather`` those book fetches, then score the
           impact ratio and emit alerts.

        The previous shape interleaved book fetches with the
        per-position loop, serialising up to N book requests per tick
        through the REST rate limiter. Batching them cuts the tick
        wall-time for a diverse whale set from O(N) round-trips to
        O(max(1, N/concurrency)).

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for whales near liquidation with impact risk.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        threshold = self._settings.liquidation_distance_threshold

        tracked = await self._storage.get_tracked_addresses()
        batch = tracked[: self._settings.liquidation_max_tracked]

        try:
            positions_by_address = await self._storage.get_latest_positions_batch(batch)
        except sqlite3.Error:
            logger.exception(
                "Failed to batch-load latest positions for %d whales",
                len(batch),
            )
            return alerts

        candidates: list[_LiquidationCandidate] = []
        for address in batch:
            for pos in positions_by_address.get(address, []):
                if pos.liquidation_price is None or pos.liquidation_price == 0:
                    continue

                mark = self._mark_prices.get(pos.coin, pos.mark_price)
                if mark == 0:
                    continue

                distance = abs(mark - pos.liquidation_price) / mark
                if distance >= threshold:
                    continue

                key = f"{address}:{pos.coin}"
                if is_on_cooldown(self._last_alert_ms, key, timestamp_ms, cooldown_ms):
                    continue

                candidates.append(
                    _LiquidationCandidate(
                        address=address,
                        coin=pos.coin,
                        size=pos.size,
                        notional_usd=pos.notional_usd,
                        mark_price=mark,
                        liq_price=pos.liquidation_price,
                        distance=distance,
                        cooldown_key=key,
                    )
                )

        if not candidates:
            return alerts

        coins = {c.coin for c in candidates}
        book_cache = await self._fetch_book_cache(coins)

        for cand in candidates:
            impact_ratio = _impact_from_cache(book_cache.get(cand.coin), cand.size)
            alerts.append(
                _liquidation_alert(
                    _LiquidationContext(
                        address=cand.address,
                        coin=cand.coin,
                        size=cand.size,
                        notional_usd=cand.notional_usd,
                        mark_price=cand.mark_price,
                        liq_price=cand.liq_price,
                        distance=cand.distance,
                        impact_ratio=impact_ratio,
                        timestamp_ms=timestamp_ms,
                    )
                )
            )
            record_alert_timestamp(self._last_alert_ms, cand.cooldown_key, timestamp_ms)

        return alerts

    async def _fetch_book_cache(self, coins: set[str]) -> dict[str, L2Book | None]:
        """Concurrently fetch L2 books for ``coins``.

        Errors per coin are absorbed and represented as ``None`` in
        the returned map so the caller can degrade impact scoring to
        zero without cascading failures across unrelated coins.
        """
        ordered = list(coins)
        results = await asyncio.gather(
            *(self._reader.get_l2_book(c) for c in ordered),
            return_exceptions=True,
        )
        cache: dict[str, L2Book | None] = {}
        for coin, result in zip(ordered, results, strict=True):
            if isinstance(result, _L2_FETCH_ERRORS):
                logger.warning("Failed to fetch L2 book for %s (%s)", coin, result)
                cache[coin] = None
            elif isinstance(result, BaseException):
                # Unknown exception types get the same treatment as
                # known network faults — liquidation scoring is
                # best-effort; one bad coin mustn't wedge the tick.
                logger.exception(
                    "Unexpected L2 book error for %s",
                    coin,
                    exc_info=result,
                )
                cache[coin] = None
            else:
                cache[coin] = result
        return cache


def _compute_impact_ratio(book: L2Book, position_size: float) -> float:
    """Compute ratio of position size to executable book depth.

    Args:
        book: Order book snapshot.
        position_size: Signed position size to liquidate.

    Returns:
        Impact ratio (abs(position) / same-side book_depth).
    """
    levels = book.bids if position_size > 0 else book.asks
    total_depth = sum(size for _, size in levels)
    if total_depth == 0 or position_size == 0:
        return float("inf")
    return abs(position_size) / total_depth


def _impact_from_cache(book: L2Book | None, position_size: float) -> float:
    """Score impact when a book may be missing from the cache.

    A ``None`` book (fetch failed) degrades to zero impact — the
    same behaviour the previous serial implementation had, kept so
    alerts still fire for near-liquidation positions even when L2
    data is momentarily unavailable.
    """
    if book is None:
        return 0.0
    return _compute_impact_ratio(book, position_size)


@dataclass(frozen=True, slots=True)
class _LiquidationCandidate:
    """Pre-scored whale position awaiting impact computation."""

    address: str
    coin: str
    size: float
    notional_usd: float
    mark_price: float
    liq_price: float
    distance: float
    cooldown_key: str


def _classify_liquidation_severity(distance: float, impact_ratio: float) -> str:
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
        severity=_classify_liquidation_severity(ctx.distance, ctx.impact_ratio),
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
