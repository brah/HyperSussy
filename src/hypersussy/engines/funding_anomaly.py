"""Funding rate anomaly detection engine.

Detects extreme or unusual funding rates by computing rolling
z-scores per coin. Alerts on statistical outliers or absolute
rate breaches.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict, deque

from hypersussy.config import HyperSussySettings
from hypersussy.models import Alert, AssetSnapshot, Trade

# Minimum hourly samples before computing z-scores
_MIN_SAMPLES = 24


class FundingAnomalyEngine:
    """Detect anomalous funding rates via rolling statistics.

    Args:
        settings: Application settings with funding thresholds.
    """

    def __init__(self, settings: HyperSussySettings) -> None:
        self._settings = settings
        # Rolling funding rate samples per coin (sampled hourly)
        self._funding_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=settings.funding_rolling_window)
        )
        # Last sample timestamp per coin
        self._last_sample_ms: dict[str, int] = {}
        # Latest funding rate per coin (for tick analysis)
        self._latest_rate: dict[str, float] = {}
        # Cooldown: coin -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "funding_anomaly"

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Sample funding rate at hourly intervals.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        self._latest_rate[snapshot.coin] = snapshot.funding_rate

        last_ts = self._last_sample_ms.get(snapshot.coin)
        if last_ts is None or snapshot.timestamp_ms - last_ts >= 3_600_000:
            self._funding_history[snapshot.coin].append(snapshot.funding_rate)
            self._last_sample_ms[snapshot.coin] = snapshot.timestamp_ms
        return []

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """No-op for this engine.

        Args:
            trade: The incoming trade.

        Returns:
            Empty list.
        """
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Check for funding rate anomalies across all coins.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for coins with anomalous funding rates.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000

        for coin, history in self._funding_history.items():
            if len(history) < _MIN_SAMPLES:
                continue

            if timestamp_ms - self._last_alert_ms.get(coin, 0) < cooldown_ms:
                continue

            current_rate = self._latest_rate.get(coin)
            if current_rate is None:
                continue

            rates = list(history)
            mean = sum(rates) / len(rates)
            variance = sum(((r - mean) ** 2 for r in rates), 0.0) / len(rates)
            stdev = math.sqrt(variance)

            zscore = (current_rate - mean) / stdev if stdev > 0 else 0.0

            is_zscore_breach = abs(zscore) >= self._settings.funding_zscore_threshold
            is_abs_breach = abs(current_rate) >= self._settings.funding_abs_threshold

            if not (is_zscore_breach or is_abs_breach):
                continue

            severity = _classify_severity(abs(zscore), abs(current_rate))
            reason = []
            if is_zscore_breach:
                reason.append(f"z-score={zscore:+.2f}")
            if is_abs_breach:
                reason.append(
                    f"rate={current_rate:+.6f} "
                    f"(>{self._settings.funding_abs_threshold})"
                )

            alerts.append(
                Alert(
                    alert_id=str(uuid.uuid4()),
                    alert_type="funding_anomaly",
                    severity=severity,
                    coin=coin,
                    title=(f"{coin}: anomalous funding ({', '.join(reason)})"),
                    description=(
                        f"{coin} funding rate {current_rate:+.6f} is "
                        f"anomalous. Rolling mean={mean:+.6f}, "
                        f"stdev={stdev:.6f}, z-score={zscore:+.2f}. "
                        f"Based on {len(rates)} hourly samples."
                    ),
                    timestamp_ms=timestamp_ms,
                    metadata={
                        "funding_rate": current_rate,
                        "rolling_mean": mean,
                        "rolling_stdev": stdev,
                        "zscore": zscore,
                        "sample_count": float(len(rates)),
                    },
                )
            )
            self._last_alert_ms[coin] = timestamp_ms

        return alerts


def _classify_severity(abs_zscore: float, abs_rate: float) -> str:
    """Classify alert severity from z-score and absolute rate.

    Args:
        abs_zscore: Absolute z-score value.
        abs_rate: Absolute funding rate.

    Returns:
        Severity string.
    """
    if abs_zscore > 5 or abs_rate > 0.005:
        return "critical"
    if abs_zscore > 4 or abs_rate > 0.002:
        return "high"
    if abs_zscore > 3 or abs_rate > 0.001:
        return "medium"
    return "low"
