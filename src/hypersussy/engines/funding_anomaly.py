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
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.models import Alert, AssetSnapshot, Trade


class FundingAnomalyEngine:
    """Detect anomalous funding rates via rolling z-score analysis.

    Computes a per-coin rolling z-score over recent funding rate samples.
    Fires when the z-score exceeds the configured threshold or when the
    absolute rate breaches its threshold.

    Args:
        settings: Application settings with funding anomaly thresholds.
    """

    _SAMPLE_INTERVAL_MS: int = 3_600_000  # one sample per hour maximum

    def __init__(self, settings: HyperSussySettings) -> None:
        self._settings = settings
        self._history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=settings.funding_rolling_window)
        )
        self._latest_rate: dict[str, float] = {}
        self._last_sampled_ms: dict[str, int] = {}
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "funding_anomaly"

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Record the latest funding rate and append to rolling history.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list.
        """
        self._latest_rate[snapshot.coin] = snapshot.funding_rate
        last = self._last_sampled_ms.get(snapshot.coin, -self._SAMPLE_INTERVAL_MS)
        if snapshot.timestamp_ms - last >= self._SAMPLE_INTERVAL_MS:
            self._history[snapshot.coin].append(snapshot.funding_rate)
            self._last_sampled_ms[snapshot.coin] = snapshot.timestamp_ms
        return []

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """Not used by this engine.

        Args:
            trade: Incoming trade (ignored).

        Returns:
            Empty list.
        """
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Evaluate z-score anomalies across all tracked coins.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            Alerts for coins with anomalous funding rates.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000

        for coin, history in self._history.items():
            if len(history) < self._settings.funding_min_samples:
                continue

            if is_on_cooldown(self._last_alert_ms, coin, timestamp_ms, cooldown_ms):
                continue

            current_rate = self._latest_rate.get(coin)
            if current_rate is None:
                continue

            n = len(history)
            mean = sum(history) / n
            variance = sum((r - mean) ** 2 for r in history) / n
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
                        f"Based on {n} hourly samples."
                    ),
                    timestamp_ms=timestamp_ms,
                    metadata={
                        "funding_rate": current_rate,
                        "rolling_mean": mean,
                        "rolling_stdev": stdev,
                        "zscore": zscore,
                        "sample_count": float(n),
                    },
                )
            )
            record_alert_timestamp(self._last_alert_ms, coin, timestamp_ms)

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
