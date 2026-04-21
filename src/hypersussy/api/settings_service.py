"""Live settings mutation, persistence, and hot-field registry.

The Config page in the dashboard writes here. Only fields in
:data:`HOT_FIELDS` are editable live — everything else is either
constructor-baked (rate limiters, deque maxlens, engine toggles) or
read once at process start (paths, URLs) and changing them at runtime
would be silently ignored or actively unsafe.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from hypersussy.config import HyperSussySettings
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hot-field registry
# ---------------------------------------------------------------------------
#
# A field is "hot" iff mutating it on the live HyperSussySettings
# instance takes effect without a restart. That requires the consumer
# to re-read ``self._settings.<field>`` on every tick (or every
# request), not bake the value into a constructor.
#
# This registry also drives the API response shape (section grouping,
# display metadata) and the frontend form. Adding a field here is the
# single source of truth.


@dataclass(frozen=True, slots=True)
class HotField:
    """Metadata describing a live-editable settings field.

    Args:
        name: Pydantic field name on ``HyperSussySettings``.
        section: UI grouping label.
        label: Short display label.
        description: One-line explanation of what the setting controls.
        minimum: Optional minimum value (inclusive) for numeric fields.
        maximum: Optional maximum value (inclusive) for numeric fields.
    """

    name: str
    section: str
    label: str
    description: str
    minimum: float | None = None
    maximum: float | None = None


_HOT_FIELD_LIST: tuple[HotField, ...] = (
    # -- OI Concentration ---------------------------------------------------
    HotField(
        "oi_change_pct_threshold",
        "OI Concentration",
        "OI change %",
        "Fraction of OI change required to trigger analysis.",
        minimum=0.0,
        maximum=10.0,
    ),
    HotField(
        "oi_concentration_top_n",
        "OI Concentration",
        "Top N addresses",
        "Number of top addresses considered when computing concentration.",
        minimum=1,
        maximum=50,
    ),
    HotField(
        "oi_concentration_threshold",
        "OI Concentration",
        "Concentration",
        "Top-N volume share required to raise an alert (0-1).",
        minimum=0.0,
        maximum=1.0,
    ),
    HotField(
        "oi_min_usd",
        "OI Concentration",
        "Min OI (USD)",
        "Coins below this OI floor are ignored.",
        minimum=0.0,
    ),
    # -- Whale Tracker ------------------------------------------------------
    HotField(
        "whale_volume_threshold_usd",
        "Whale Tracker",
        "Volume threshold",
        "Rolling volume above which an address is promoted to whale.",
        minimum=0.0,
    ),
    HotField(
        "whale_discovery_oi_pct",
        "Whale Tracker",
        "OI promotion %",
        "Fraction of coin OI an address must trade to be promoted.",
        minimum=0.0,
        maximum=1.0,
    ),
    HotField(
        "whale_oi_min_notional_usd",
        "Whale Tracker",
        "Min notional (OI path)",
        "Minimum position size for OI-path whale promotion.",
        minimum=0.0,
    ),
    HotField(
        "whale_volume_lookback_ms",
        "Whale Tracker",
        "Volume lookback (ms)",
        "Rolling window for whale volume totals.",
        minimum=60_000,
    ),
    HotField(
        "max_tracked_addresses",
        "Whale Tracker",
        "Max tracked",
        "Upper bound on in-memory tracked whales.",
        minimum=1,
        maximum=10_000,
    ),
    HotField(
        "position_poll_interval_s",
        "Whale Tracker",
        "Poll interval (s)",
        "Seconds between whale position polls.",
        minimum=5.0,
    ),
    HotField(
        "large_position_oi_pct",
        "Whale Tracker",
        "Large pos OI %",
        "Fraction of coin OI a position must reach to count as large.",
        minimum=0.0,
        maximum=1.0,
    ),
    HotField(
        "large_position_min_oi_usd",
        "Whale Tracker",
        "Large pos min OI (USD)",
        "Coin OI floor for large-position eligibility.",
        minimum=0.0,
    ),
    HotField(
        "large_position_change_usd",
        "Whale Tracker",
        "Pos change (USD)",
        "Minimum notional change between polls to emit an alert.",
        minimum=0.0,
    ),
    HotField(
        "whale_poll_batch_size",
        "Whale Tracker",
        "Poll batch size",
        "Whales polled in parallel per tick.",
        minimum=1,
        maximum=100,
    ),
    # -- Position Census ----------------------------------------------------
    HotField(
        "census_poll_interval_s",
        "Position Census",
        "Census interval (s)",
        "Seconds between non-whale position polls.",
        minimum=5.0,
    ),
    HotField(
        "census_poll_batch_size",
        "Position Census",
        "Census batch",
        "Addresses polled per census tick.",
        minimum=1,
        maximum=50,
    ),
    HotField(
        "census_min_volume_usd",
        "Position Census",
        "Min volume (USD)",
        "Volume floor for a non-whale address to be polled.",
        minimum=0.0,
    ),
    HotField(
        "census_volume_lookback_ms",
        "Position Census",
        "Volume lookback (ms)",
        "Rolling window for census volume totals.",
        minimum=60_000,
    ),
    # -- Pre-Move -----------------------------------------------------------
    HotField(
        "pre_move_threshold_pct",
        "Pre-Move",
        "Move %",
        "Price move required to trigger pre-move analysis.",
        minimum=0.0,
        maximum=1.0,
    ),
    HotField(
        "pre_move_min_notional_usd",
        "Pre-Move",
        "Min notional (USD)",
        "Minimum pre-move notional per address for inclusion.",
        minimum=0.0,
    ),
    HotField(
        "pre_move_top_n",
        "Pre-Move",
        "Top N",
        "Number of aligned addresses included in pre-move alerts.",
        minimum=1,
        maximum=50,
    ),
    HotField(
        "pre_move_cooldown_ms",
        "Pre-Move",
        "Cooldown (ms)",
        "Per-coin cooldown between pre-move alerts.",
        minimum=0,
    ),
    # -- Funding Anomaly ----------------------------------------------------
    HotField(
        "funding_zscore_threshold",
        "Funding Anomaly",
        "Z-score",
        "Rolling funding z-score required to alert.",
        minimum=0.0,
    ),
    HotField(
        "funding_abs_threshold",
        "Funding Anomaly",
        "Abs rate",
        "Absolute funding rate required to alert.",
        minimum=0.0,
    ),
    HotField(
        "funding_rolling_window",
        "Funding Anomaly",
        "Rolling window (hours)",
        "Number of hourly samples for the rolling mean/stdev.",
        minimum=2,
        maximum=720,
    ),
    HotField(
        "funding_min_samples",
        "Funding Anomaly",
        "Min samples",
        "Minimum samples required before evaluating the window.",
        minimum=2,
        maximum=720,
    ),
    HotField(
        "funding_sample_interval_ms",
        "Funding Anomaly",
        "Sample interval (ms)",
        "Minimum spacing between rolling-window samples. Defaults "
        "to 1 h because HL funding updates roughly hourly.",
        minimum=60_000,
        maximum=86_400_000,
    ),
    # -- Liquidation Risk ---------------------------------------------------
    HotField(
        "liquidation_distance_threshold",
        "Liquidation Risk",
        "Distance",
        "Fractional distance-to-liquidation threshold for alerts.",
        minimum=0.0,
        maximum=1.0,
    ),
    # -- Alerting -----------------------------------------------------------
    HotField(
        "alert_cooldown_s",
        "Alerting",
        "Cooldown (s)",
        "Per-fingerprint dedup window for alerts.",
        minimum=0,
    ),
    HotField(
        "alert_max_per_minute",
        "Alerting",
        "Rate limit",
        "Global alert dispatch rate ceiling.",
        minimum=1,
        maximum=1000,
    ),
    # -- Polling ------------------------------------------------------------
    HotField(
        "meta_poll_interval_s",
        "Polling",
        "Meta poll (s)",
        "Seconds between metaAndAssetCtxs polls.",
        minimum=1.0,
    ),
    HotField(
        "engine_tick_interval_s",
        "Polling",
        "Engine tick (s)",
        "Seconds between engine tick() calls.",
        minimum=1.0,
    ),
    HotField(
        "asset_list_refresh_s",
        "Polling",
        "Asset list refresh (s)",
        "Seconds between coin universe refreshes.",
        minimum=10.0,
    ),
    # -- Retention ----------------------------------------------------------
    HotField(
        "trades_retention_days",
        "Retention",
        "Trades (days)",
        "Delete trade rows older than this. 0 disables.",
        minimum=0,
        maximum=365,
    ),
    HotField(
        "asset_snapshots_retention_days",
        "Retention",
        "Snapshots (days)",
        "Delete asset snapshot rows older than this. 0 disables.",
        minimum=0,
        maximum=365,
    ),
    HotField(
        "address_positions_retention_days",
        "Retention",
        "Positions (days)",
        "Delete address position rows older than this. 0 disables.",
        minimum=0,
        maximum=365,
    ),
    HotField(
        "retention_interval_s",
        "Retention",
        "Sweep interval (s)",
        "Seconds between retention loop ticks.",
        minimum=60.0,
    ),
    # -- Candles ------------------------------------------------------------
    HotField(
        "candles_page_size",
        "Candles",
        "Page size (bars)",
        "Bars returned per /api/candles page. Larger = fewer round trips "
        "on deep scroll; smaller = faster first paint.",
        minimum=100,
        maximum=10_000,
    ),
    HotField(
        "candles_max_backfill_chunks",
        "Candles",
        "Max backfill chunks",
        "Safety cap on HL backfill round trips per page request. One "
        "chunk pulls up to 5000 bars — 8 chunks ≈ 40k bars max per call.",
        minimum=1,
        maximum=32,
    ),
)

HOT_FIELDS: dict[str, HotField] = {f.name: f for f in _HOT_FIELD_LIST}


class SettingsUpdateError(ValueError):
    """Raised when a config update fails validation or targets a cold field."""


def apply_persisted_overrides(
    settings: HyperSussySettings,
    overrides: dict[str, str],
) -> None:
    """Merge persisted overrides onto the live settings instance.

    Called once at application startup after ``HyperSussySettings()``
    has loaded env + defaults. Any override targeting a field outside
    the hot registry, or that fails Pydantic validation, is logged
    and skipped so a corrupt row can't take the runner offline.

    Args:
        settings: The live settings instance to mutate in place.
        overrides: Mapping of field name to JSON-encoded string value
            (as stored in the ``settings_overrides`` SQLite table).
    """
    for key, raw in overrides.items():
        if key not in HOT_FIELDS:
            logger.warning(
                "Ignoring persisted override for non-hot field %r",
                key,
            )
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed JSON for override %r: %r", key, raw)
            continue
        try:
            _apply_validated(settings, key, value)
        except SettingsUpdateError as exc:
            logger.warning("Ignoring invalid persisted override %r: %s", key, exc)


def update_field(
    settings: HyperSussySettings,
    key: str,
    value: Any,
) -> Any:
    """Validate and apply a single field update to the live settings.

    Args:
        settings: Live settings instance to mutate in place.
        key: Field name to update (must be in :data:`HOT_FIELDS`).
        value: New value. Any JSON-compatible scalar; Pydantic will
            coerce/validate against the field's declared type.

    Returns:
        The validated, coerced value that was applied.

    Raises:
        SettingsUpdateError: If the field is not hot-editable or the
            value fails Pydantic validation.
    """
    if key not in HOT_FIELDS:
        msg = f"field {key!r} is not live-editable"
        raise SettingsUpdateError(msg)
    return _apply_validated(settings, key, value)


def _apply_validated(
    settings: HyperSussySettings,
    key: str,
    value: Any,
) -> Any:
    """Run the new value through Pydantic validation then ``setattr``.

    Building a fresh :class:`HyperSussySettings` with the current
    values plus the candidate override forces Pydantic to run the
    full validator on the updated field, without needing
    ``validate_assignment = True`` on the model itself (which would
    impose a per-set cost on every code path that mutates settings).

    Args:
        settings: The live settings instance.
        key: Field name to update.
        value: Candidate value.

    Returns:
        The coerced value extracted from the validated instance.

    Raises:
        SettingsUpdateError: If Pydantic rejects the candidate.
    """
    current = settings.model_dump()
    current[key] = value
    try:
        validated = HyperSussySettings(**current)
    except ValidationError as exc:
        raise SettingsUpdateError(str(exc)) from exc
    coerced = getattr(validated, key)
    setattr(settings, key, coerced)
    return coerced


async def persist_override(
    storage: StorageProtocol,
    key: str,
    value: Any,
) -> None:
    """Write an override to the settings_overrides table.

    Args:
        storage: Async storage backend.
        key: Setting field name.
        value: Value to persist (JSON-encoded before write).
    """
    await storage.upsert_settings_override(key, json.dumps(value))


async def clear_override(
    storage: StorageProtocol,
    key: str,
) -> None:
    """Remove a persisted override (reverts to env/default on next load).

    Args:
        storage: Async storage backend.
        key: Setting field name.
    """
    await storage.delete_settings_override(key)
