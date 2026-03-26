"""Pre-move correlation engine.

Detects addresses that traded heavily in a direction shortly
before a large price move, indicating possible informed trading.
"""

from __future__ import annotations

import uuid
from bisect import bisect_left
from collections import defaultdict, deque

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.models import Alert, AssetSnapshot, Trade

class PreMoveEngine:
    """Retroactively identify pre-move trading activity.

    Args:
        settings: Application settings with pre-move thresholds.
    """

    def __init__(self, settings: HyperSussySettings) -> None:
        self._settings = settings
        # Price ring buffer: coin -> deque of (timestamp_ms, mark_price)
        self._prices: dict[str, deque[tuple[int, float]]] = defaultdict(
            lambda: deque(maxlen=settings.pre_move_price_maxlen)
        )
        # Trade buffer: coin -> deque of (ts, buyer, seller, price, size)
        self._trades: dict[str, deque[tuple[int, str, str, float, float]]] = (
            defaultdict(lambda: deque(maxlen=settings.pre_move_trade_maxlen))
        )
        # Cooldown: coin -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "pre_move"

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Record price for move detection.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        self._prices[snapshot.coin].append((snapshot.timestamp_ms, snapshot.mark_price))
        return []

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Buffer trade for pre-move lookback.

        Args:
            trade: The incoming trade.

        Returns:
            Empty list.
        """
        self._trades[trade.coin].append(
            (
                trade.timestamp_ms,
                trade.buyer,
                trade.seller,
                trade.price,
                trade.size,
            )
        )
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Check for large price moves and analyze pre-move activity.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for addresses with aligned pre-move activity.
        """
        alerts: list[Alert] = []

        for coin, prices in self._prices.items():
            if len(prices) < 2:
                continue

            # Cooldown check
            if is_on_cooldown(
                self._last_alert_ms,
                coin,
                timestamp_ms,
                self._settings.pre_move_cooldown_ms,
            ):
                continue

            current_price = prices[-1][1]

            for window_ms in self._settings.pre_move_windows_ms:
                cutoff = timestamp_ms - window_ms
                start_price = _find_price_at(prices, cutoff)
                if start_price is None or start_price == 0:
                    continue

                ret = (current_price - start_price) / start_price
                if abs(ret) < self._settings.pre_move_threshold_pct:
                    continue

                # Large move detected -- analyze pre-move trading
                pre_start = cutoff - self._settings.pre_move_lookback_ms
                alert = self._analyze_pre_move(
                    coin, ret, pre_start, cutoff, timestamp_ms
                )
                if alert:
                    alerts.append(alert)
                    record_alert_timestamp(self._last_alert_ms, coin, timestamp_ms)
                    break  # One alert per coin per tick

        return alerts

    def _analyze_pre_move(
        self,
        coin: str,
        price_return: float,
        pre_start: int,
        pre_end: int,
        timestamp_ms: int,
    ) -> Alert | None:
        """Find addresses with aligned trading before the move.

        Args:
            coin: Asset name.
            price_return: The price return (signed).
            pre_start: Start of the pre-move window.
            pre_end: End of the pre-move window (move start).
            timestamp_ms: Current timestamp.

        Returns:
            Alert if aligned addresses found, else None.
        """
        trades = self._trades.get(coin)
        if not trades:
            return None

        # Binary search for window boundaries (trades sorted by timestamp)
        start_idx = bisect_left(trades, (pre_start,))
        end_idx = bisect_left(trades, (pre_end,))

        # Net flow per address: positive = net long, negative = net short
        addr_flow: dict[str, float] = {}
        for i in range(start_idx, end_idx):
            _, buyer, seller, price, size = trades[i]
            notional = price * size
            if buyer:
                addr_flow[buyer] = addr_flow.get(buyer, 0.0) + notional
            if seller:
                addr_flow[seller] = addr_flow.get(seller, 0.0) - notional

        move_sign = 1.0 if price_return > 0 else -1.0
        min_notional = self._settings.pre_move_min_notional_usd

        aligned = [
            (addr, flow)
            for addr, flow in addr_flow.items()
            if flow * move_sign > 0 and abs(flow) >= min_notional
        ]

        if not aligned:
            return None

        aligned.sort(key=lambda x: abs(x[1]), reverse=True)
        top = aligned[: self._settings.pre_move_top_n]

        top_addresses = [addr for addr, _ in top]
        top_flows = [flow for _, flow in top]
        total_aligned = sum(abs(f) for f in top_flows)
        direction = "bought" if move_sign > 0 else "sold"
        severity = (
            "critical"
            if total_aligned > 10_000_000
            else "high"
            if total_aligned > 2_000_000
            else "medium"
        )

        return Alert(
            alert_id=str(uuid.uuid4()),
            alert_type="pre_move",
            severity=severity,
            coin=coin,
            title=(
                f"{coin}: {len(top)} address(es) {direction} "
                f"${total_aligned:,.0f} before {price_return:+.1%} move"
            ),
            description=(
                f"{coin} moved {price_return:+.1%}. Top {len(top)} "
                f"aligned addresses {direction} a combined "
                f"${total_aligned:,.0f} in the preceding "
                f"{self._settings.pre_move_lookback_ms // 60_000}min."
            ),
            timestamp_ms=timestamp_ms,
            metadata={
                "price_return": price_return,
                "top_addresses": top_addresses,
                "total_aligned_usd": total_aligned,
            },
        )


def _find_price_at(prices: deque[tuple[int, float]], target_ms: int) -> float | None:
    """Find the price at or just after a target timestamp via binary search.

    Args:
        prices: Sorted deque of (timestamp_ms, price).
        target_ms: Target timestamp.

    Returns:
        Price at the target time, or None if not found.
    """
    n = len(prices)
    if n == 0:
        return None
    lo, hi = 0, n - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if prices[mid][0] < target_ms:
            lo = mid + 1
        else:
            hi = mid
    if prices[lo][0] >= target_ms:
        return prices[lo][1]
    return None
