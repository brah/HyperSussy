"""Open Interest concentration detection engine.

Detects rapid OI changes and checks whether a small number of
addresses account for a disproportionate share of the trading
volume during that period.
"""

from __future__ import annotations

import uuid
from bisect import bisect_left
from collections import defaultdict, deque

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.models import Alert, AssetSnapshot, Trade
from hypersussy.storage.base import StorageProtocol


class OiConcentrationEngine:
    """Detect OI spikes concentrated in few addresses.

    Args:
        storage: Storage backend for trade volume queries.
        settings: Application settings with thresholds.
    """

    def __init__(
        self,
        storage: StorageProtocol,
        settings: HyperSussySettings,
    ) -> None:
        self._storage = storage
        self._settings = settings
        # Ring buffer per coin: deque of (timestamp_ms, oi_usd)
        self._oi_history: dict[str, deque[tuple[int, float]]] = defaultdict(
            lambda: deque(maxlen=settings.oi_history_maxlen)
        )
        # Cooldown tracking: coin -> last alert timestamp_ms
        self._last_alert_ms: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Unique name identifying this engine."""
        return "oi_concentration"

    async def on_asset_update(self, snapshot: AssetSnapshot) -> list[Alert]:
        """Ingest an asset snapshot into the OI ring buffer.

        Args:
            snapshot: Updated asset snapshot.

        Returns:
            Empty list (analysis happens in tick).
        """
        if snapshot.open_interest_usd < self._settings.oi_min_usd:
            return []
        self._oi_history[snapshot.coin].append(
            (snapshot.timestamp_ms, snapshot.open_interest_usd)
        )
        return []

    async def tick(self, timestamp_ms: int) -> list[Alert]:
        """Analyze OI changes across all tracked coins.

        For each coin, checks if OI changed beyond threshold in any
        configured window, then queries trade data to check if the
        activity is concentrated in few addresses.

        Args:
            timestamp_ms: Current timestamp in milliseconds.

        Returns:
            List of alerts for coins with concentrated OI changes.
        """
        alerts: list[Alert] = []
        cooldown_ms = self._settings.alert_cooldown_s * 1000

        # Snapshot the dict before iterating: the loop body awaits inside
        # _check_window, during which on_asset_update can land on the same
        # event loop and insert a brand-new coin into self._oi_history.
        # Iterating the live dict across those awaits raises
        # "dictionary changed size during iteration". Any coin added after
        # the snapshot is fine to skip for this tick — it'll be picked up
        # on the next one.
        for coin, history in list(self._oi_history.items()):
            if len(history) < 2:
                continue

            # Skip if recently alerted
            if is_on_cooldown(self._last_alert_ms, coin, timestamp_ms, cooldown_ms):
                continue

            current_oi = history[-1][1]
            if current_oi < self._settings.oi_min_usd:
                continue

            for window_ms in self._settings.oi_change_windows_ms:
                alert = await self._check_window(
                    coin, current_oi, timestamp_ms, window_ms
                )
                if alert:
                    alerts.append(alert)
                    record_alert_timestamp(self._last_alert_ms, coin, timestamp_ms)
                    break  # One alert per coin per tick

        return alerts

    async def _check_window(
        self,
        coin: str,
        current_oi: float,
        now_ms: int,
        window_ms: int,
    ) -> Alert | None:
        """Check a single time window for OI concentration.

        Args:
            coin: Asset name.
            current_oi: Current OI in USD.
            now_ms: Current timestamp.
            window_ms: Lookback window in milliseconds.

        Returns:
            An Alert if thresholds are breached, else None.
        """
        history = self._oi_history[coin]
        cutoff = now_ms - window_ms

        # Binary search for the first entry >= cutoff
        idx = bisect_left(history, (cutoff,))
        if idx >= len(history):
            return None
        start_oi = history[idx][1]

        if start_oi == 0:
            return None

        delta_pct = (current_oi - start_oi) / start_oi
        if abs(delta_pct) < self._settings.oi_change_pct_threshold:
            return None

        # OI changed significantly -- check address concentration
        (
            top_addresses,
            total_volume,
        ) = await self._storage.get_top_addresses_and_total_volume(
            coin, cutoff, self._settings.oi_concentration_top_n
        )

        if not top_addresses or total_volume == 0:
            return None

        top_volume = sum(vol for _, vol in top_addresses)
        concentration = top_volume / total_volume

        if concentration < self._settings.oi_concentration_threshold:
            return None

        window_label = _format_window(window_ms)
        direction = "increased" if delta_pct > 0 else "decreased"
        severity = _classify_severity(abs(delta_pct), concentration)
        top_addrs_list = [addr for addr, _ in top_addresses]

        return Alert(
            alert_id=str(uuid.uuid4()),
            alert_type="oi_concentration",
            severity=severity,
            coin=coin,
            title=(f"{coin} OI {direction} {abs(delta_pct):.1%} in {window_label}"),
            description=(
                f"Open interest {direction} from "
                f"${start_oi:,.0f} to ${current_oi:,.0f} "
                f"({delta_pct:+.1%}) over {window_label}. "
                f"Top {len(top_addresses)} addresses account for "
                f"{concentration:.0%} of volume "
                f"(${top_volume:,.0f} / ${total_volume:,.0f})."
            ),
            timestamp_ms=now_ms,
            metadata={
                "delta_pct": delta_pct,
                "start_oi_usd": start_oi,
                "current_oi_usd": current_oi,
                "window_ms": float(window_ms),
                "concentration": concentration,
                "top_volume_usd": top_volume,
                "total_volume_usd": total_volume,
                "top_addresses": top_addrs_list,
            },
        )

    async def on_trade(self, trade: Trade) -> list[Alert]:
        """No-op for this engine (trade data used via storage).

        Args:
            trade: The incoming trade.

        Returns:
            Empty list.
        """
        return []


def _format_window(window_ms: int) -> str:
    """Format a millisecond window into a human-readable string.

    Args:
        window_ms: Window duration in milliseconds.

    Returns:
        Formatted string like "5m", "15m", "1h".
    """
    minutes = window_ms // 60_000
    if minutes >= 60:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def _classify_severity(delta_pct: float, concentration: float) -> str:
    """Classify alert severity based on OI change and concentration.

    Args:
        delta_pct: Absolute OI change percentage.
        concentration: Top-N address volume concentration ratio.

    Returns:
        Severity string: "low", "medium", "high", or "critical".
    """
    score = delta_pct * concentration
    if score > 0.15:
        return "critical"
    if score > 0.08:
        return "high"
    if score > 0.04:
        return "medium"
    return "low"
