"""Shared helpers for detection engines."""

from __future__ import annotations

# (cutoff, label) pairs in *descending* cutoff order. The first cutoff
# whose threshold is exceeded by the score wins.
SeverityCutoffs = tuple[tuple[float, str], ...]


def is_on_cooldown(
    last_alert_ms: dict[str, int],
    key: str,
    timestamp_ms: int,
    cooldown_ms: int,
) -> bool:
    """Return whether a per-key cooldown is still active."""
    if key not in last_alert_ms:
        return False
    return timestamp_ms - last_alert_ms[key] < cooldown_ms


def record_alert_timestamp(
    last_alert_ms: dict[str, int],
    key: str,
    timestamp_ms: int,
) -> None:
    """Record the latest alert timestamp for a cooldown key."""
    last_alert_ms[key] = timestamp_ms


def classify_severity(
    score: float,
    cutoffs: SeverityCutoffs,
    *,
    default: str = "low",
) -> str:
    """Map a normalised score to a severity label.

    Each engine had its own ladder of ``if score > X: return "..."``
    branches that differed only in the (cutoff, label) pairs. This
    helper centralises the loop so the per-engine code keeps just the
    cutoff tuple — the actual thresholds are intentionally per-engine,
    only the matching logic is shared.

    Args:
        score: Score to classify (any monotonic combination of
            engine-specific signals).
        cutoffs: Tuple of ``(threshold, label)`` pairs in descending
            threshold order. The first pair whose threshold is
            exceeded wins.
        default: Label returned when no cutoff matches.

    Returns:
        The matching severity label, or ``default`` if no cutoff
        matches.
    """
    for threshold, label in cutoffs:
        if score > threshold:
            return label
    return default
