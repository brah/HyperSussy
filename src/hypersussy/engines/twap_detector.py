"""TWAP (Time-Weighted Average Price) execution detection engine.

Detects evenly-spaced fill patterns indicative of algorithmic
TWAP execution by scoring coefficient-of-variation of inter-fill
times and fill sizes.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict, deque

from hypersussy.config import HyperSussySettings
from hypersussy.models import Alert, AssetSnapshot, Trade


class TwapDetectorEngine:
    """Detect TWAP execution patterns from trade flow.

    Args:
        settings: Application settings with TWAP thresholds.
    """

    def __init__(self, settings: HyperSussySettings) -> None:
        self._settings = settings
        # (address, coin, direction) -> deque of (timestamp_ms, size)
        self._fills: dict[tuple[str, str, str], deque[tuple[int, float]]] = defaultdict(
            lambda: deque(maxlen=5000)
        )
        # Cooldown: key -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "twap_detector"

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Record fill for buyer and seller.

        Args:
            trade: The incoming trade.

        Returns:
            Empty list (analysis happens in tick).
        """
        for addr, direction in (
            (trade.buyer, "buy"),
            (trade.seller, "sell"),
        ):
            if not addr:
                continue
            key = (addr, trade.coin, direction)
            self._fills[key].append((trade.timestamp_ms, trade.size))
        return []

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """No-op for this engine.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Prune old fills and score for TWAP patterns.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for detected TWAP executions.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000
        cutoff = timestamp_ms - self._settings.twap_window_ms

        keys_to_remove: list[tuple[str, str, str]] = []

        for key, fills in self._fills.items():
            # Prune entries outside the window
            while fills and fills[0][0] < cutoff:
                fills.popleft()

            if len(fills) < self._settings.twap_min_fills:
                if not fills:
                    keys_to_remove.append(key)
                continue

            addr, coin, direction = key
            cooldown_key = f"{addr}:{coin}:{direction}"
            if timestamp_ms - self._last_alert_ms.get(cooldown_key, 0) < cooldown_ms:
                continue

            timestamps = [f[0] for f in fills]
            sizes = [f[1] for f in fills]
            total_notional_approx = sum(sizes)  # size only, price unknown

            # Use size sum as rough proxy; real notional tracked below
            intervals = [
                float(timestamps[i + 1] - timestamps[i])
                for i in range(len(timestamps) - 1)
            ]
            time_cv = _cv(intervals)
            size_cv = _cv(sizes)

            if (
                time_cv > self._settings.twap_max_time_cv
                or size_cv > self._settings.twap_max_size_cv
            ):
                continue

            # Recompute with actual fills data
            fill_count = len(fills)
            score = fill_count / ((1 + time_cv) * (1 + size_cv))

            alert = _twap_alert(
                addr,
                coin,
                direction,
                fill_count,
                time_cv,
                size_cv,
                score,
                total_notional_approx,
                timestamp_ms,
            )
            alerts.append(alert)
            self._last_alert_ms[cooldown_key] = timestamp_ms

        for key in keys_to_remove:
            del self._fills[key]

        return alerts


def _cv(values: list[float]) -> float:
    """Compute coefficient of variation (stdev / mean).

    Args:
        values: Numeric values.

    Returns:
        CV ratio, or inf if insufficient data or zero mean.
    """
    n = len(values)
    if n < 2:
        return float("inf")
    mean = sum(values) / n
    if mean == 0:
        return float("inf")
    variance = sum(((v - mean) ** 2 for v in values), 0.0) / (n - 1)
    return math.sqrt(variance) / abs(mean)


def _twap_alert(
    address: str,
    coin: str,
    direction: str,
    fill_count: int,
    time_cv: float,
    size_cv: float,
    score: float,
    total_size: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for detected TWAP execution.

    Args:
        address: Address executing the TWAP.
        coin: Asset name.
        direction: "buy" or "sell".
        fill_count: Number of fills in the window.
        time_cv: Coefficient of variation of inter-fill times.
        size_cv: Coefficient of variation of fill sizes.
        score: TWAP likelihood score.
        total_size: Total size across fills.
        timestamp_ms: Alert timestamp.

    Returns:
        A twap_detected alert.
    """
    severity = "high" if score > 50 else "medium" if score > 20 else "low"
    return Alert(
        alert_id=str(uuid.uuid4()),
        alert_type="twap_detected",
        severity=severity,
        coin=coin,
        title=(
            f"{coin}: TWAP {direction} detected ({fill_count} fills, score={score:.1f})"
        ),
        description=(
            f"Address {address[:10]}... executing probable TWAP {direction} "
            f"on {coin}: {fill_count} fills, time_cv={time_cv:.3f}, "
            f"size_cv={size_cv:.3f}, total_size={total_size:.4f}."
        ),
        timestamp_ms=timestamp_ms,
        metadata={
            "address": address,
            "direction": direction,
            "fill_count": float(fill_count),
            "time_cv": time_cv,
            "size_cv": size_cv,
            "score": score,
            "total_size": total_size,
        },
    )
