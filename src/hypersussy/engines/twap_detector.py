"""Detects TWAP orders from API fills."""

from __future__ import annotations

import uuid
from typing import Any, cast

from hypersussy.config import HyperSussySettings
from hypersussy.engines._shared import is_on_cooldown, record_alert_timestamp
from hypersussy.models import Alert, TwapSliceFill


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
        """Process pre-fetched TWAP slice fills into alerts.

        Malformed fill payloads (missing ``twapId``, ``fill``, or any
        of the nested ``time``/``coin``/``side``/``px``/``sz`` keys)
        are skipped with a single per-process warning. ``TypedDict``
        declarations pin the expected shape for mypy but don't
        enforce it at runtime, so we can't assume every API response
        is well-formed.
        """
        if not fills:
            return []

        cooldown_ms = self._settings.alert_cooldown_s * 1000

        # Group by twapId, keeping only the latest fill per TWAP.
        # ``TypedDict`` pins the shape for mypy but doesn't enforce
        # it at runtime; look up via ``dict.get`` on a plain dict
        # view so a malformed payload degrades to "skip this entry"
        # instead of a KeyError that propagates out of the engine
        # loop.
        twap_latest: dict[int, dict[str, Any]] = {}
        for entry in fills:
            entry_dict = cast(dict[str, Any], entry)
            twap_id = entry_dict.get("twapId")
            fill = entry_dict.get("fill")
            if twap_id is None or not isinstance(fill, dict):
                continue
            fill_time = fill.get("time")
            if fill_time is None:
                continue
            prev = twap_latest.get(twap_id)
            if prev is None or fill_time > prev.get("time", 0):
                twap_latest[twap_id] = fill

        alerts: list[Alert] = []
        active_window_ms = (
            int(self._settings.position_poll_interval_s * 1000)
            * self._settings.twap_active_window_multiplier
        )

        for twap_id, fill_dict in twap_latest.items():
            fill_time = fill_dict.get("time", 0)
            if timestamp_ms - fill_time > active_window_ms:
                continue

            key = f"{addr}:twap:{twap_id}"
            if is_on_cooldown(self._last_alert_ms, key, timestamp_ms, cooldown_ms):
                continue

            coin = fill_dict.get("coin", "")
            side = fill_dict.get("side", "")
            raw_sz = fill_dict.get("sz")
            raw_px = fill_dict.get("px")
            if not coin or raw_sz is None or raw_px is None:
                continue
            try:
                sz = float(raw_sz)
                px = float(raw_px)
            except (TypeError, ValueError):
                continue
            is_buy = side == "B"

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
            "twap_id": twap_id,
            "direction": direction,
            "slice_sz": slice_sz,
            "slice_px": slice_px,
        },
    )
