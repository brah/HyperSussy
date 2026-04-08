"""Shared "is this `hours` query within retention?" check.

Both ``/api/snapshots/{oi,funding}`` and ``/api/trades/{top-whales,
top-holders,flow}`` clamp their ``hours`` parameter to whatever the
matching retention setting allows. The two route modules used to
each carry their own pair of helpers (``_max_*_hours`` +
``_check_*_hours``); this module replaces both with a single
parameterised helper.
"""

from __future__ import annotations

from fastapi import HTTPException

from hypersussy.config import HyperSussySettings

# Outer ceiling for Pydantic validation. The dynamic per-request cap
# derived from the live retention setting is enforced inside the
# handler — this constant just guards against runaway numeric inputs
# at the framework boundary and matches the historical 30-day cap.
HARD_MAX_HOURS = 720


def max_hours_for(settings: HyperSussySettings, *, days_field: str) -> int:
    """Return the effective max lookback window for a route.

    Args:
        settings: Live :class:`HyperSussySettings` instance.
        days_field: Name of the retention-days attribute on settings
            (e.g. ``"trades_retention_days"``).

    Returns:
        Capped lookback in hours. Falls back to :data:`HARD_MAX_HOURS`
        when retention is disabled (days <= 0).
    """
    days = getattr(settings, days_field)
    if days > 0:
        return int(days) * 24
    return HARD_MAX_HOURS


def check_hours_within_retention(
    hours: int,
    settings: HyperSussySettings,
    *,
    days_field: str,
    label: str,
) -> None:
    """Raise 422 if ``hours`` exceeds the live retention window.

    Args:
        hours: User-supplied lookback window.
        settings: Live :class:`HyperSussySettings` instance.
        days_field: Name of the retention-days attribute on settings.
        label: Short label of the relevant store, used in the error
            detail (e.g. ``"trades"``, ``"asset_snapshots"``).

    Raises:
        HTTPException: 422 if ``hours`` is beyond the retention cap.
    """
    cap = max_hours_for(settings, days_field=days_field)
    if hours > cap:
        raise HTTPException(
            status_code=422,
            detail=(
                f"hours={hours} exceeds {label} retention window ({cap}h). "
                f"Increase {days_field} to query further back."
            ),
        )
