"""Tests for shared engine helpers."""

from __future__ import annotations

from hypersussy.engines._shared import (
    classify_severity,
    is_on_cooldown,
    record_alert_timestamp,
)


class TestClassifySeverity:
    """Tests for the descending-cutoff severity classifier."""

    def test_first_matching_cutoff_wins(self) -> None:
        cutoffs = (
            (10.0, "critical"),
            (5.0, "high"),
            (1.0, "medium"),
        )
        assert classify_severity(15.0, cutoffs) == "critical"
        assert classify_severity(7.0, cutoffs) == "high"
        assert classify_severity(2.0, cutoffs) == "medium"

    def test_below_lowest_cutoff_returns_default(self) -> None:
        cutoffs = ((10.0, "critical"), (5.0, "high"))
        assert classify_severity(0.5, cutoffs) == "low"
        assert classify_severity(0.5, cutoffs, default="medium") == "medium"

    def test_strict_inequality(self) -> None:
        # Edge: a score equal to a cutoff does NOT match (the helper
        # uses ``>`` to mirror the original engine semantics).
        cutoffs = ((5.0, "high"),)
        assert classify_severity(5.0, cutoffs) == "low"
        assert classify_severity(5.0001, cutoffs) == "high"

    def test_empty_cutoffs_returns_default(self) -> None:
        assert classify_severity(99.0, ()) == "low"
        assert classify_severity(99.0, (), default="medium") == "medium"


class TestCooldown:
    """Sanity tests for the existing cooldown helpers."""

    def test_first_call_is_not_on_cooldown(self) -> None:
        assert is_on_cooldown({}, "k", 1000, 500) is False

    def test_within_window_is_on_cooldown(self) -> None:
        last = {"k": 800}
        assert is_on_cooldown(last, "k", 1000, 500) is True

    def test_outside_window_is_not_on_cooldown(self) -> None:
        last = {"k": 100}
        assert is_on_cooldown(last, "k", 1000, 500) is False

    def test_record_overwrites(self) -> None:
        last: dict[str, int] = {}
        record_alert_timestamp(last, "k", 1000)
        record_alert_timestamp(last, "k", 2000)
        assert last["k"] == 2000
