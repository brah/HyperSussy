"""Detects TWAP orders from API fills."""

from __future__ import annotations

import uuid

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.models import Alert, TwapFillEntry, TwapSliceFill


class TwapDetector:
    """Detects active TWAP orders from API fills."""

    def __init__(self, settings: HyperSussySettings) -> None:
        self._settings = settings
        self._last_alert_ms: dict[str, int] = {}

    def process_twap_fills(
        self,
        addr: str,
        fills: list[TwapSliceFill],
        timestamp_ms: int,
    ) -> list[Alert]:
        """Process pre-fetched TWAP slice fills into alerts."""
        if not fills:
            return []

        cooldown_ms = self._settings.alert_cooldown_s * 1000

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
        active_window_ms = (
            int(self._settings.position_poll_interval_s * 1000)
            * self._settings.twap_active_window_multiplier
        )

        for twap_id, latest_fill in twap_latest.items():
            fill_time = latest_fill["time"]
            if timestamp_ms - fill_time > active_window_ms:
                continue

            key = f"{addr}:twap:{twap_id}"
            if is_on_cooldown(self._last_alert_ms, key, timestamp_ms, cooldown_ms):
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
            record_alert_timestamp(self._last_alert_ms, key, timestamp_ms)

        return alerts


def _twap_active_alert(
    address: str,
    coin: str,
    twap_id: int,
    direction: str,
    slice_sz: float,
    slice_px: float,
    timestamp_ms: int,
) -> Alert:
    """Create an alert for a confirmed active TWAP execution."""
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
