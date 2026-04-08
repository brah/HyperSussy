"""Tests for the live-editable settings service."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.api.settings_service import (
    HOT_FIELDS,
    SettingsUpdateError,
    apply_persisted_overrides,
    update_field,
)
from hypersussy.config import HyperSussySettings


class TestUpdateField:
    """Unit tests for validating and mutating settings fields."""

    def test_updates_numeric_field_in_place(self) -> None:
        """A valid numeric update mutates the live instance."""
        settings = HyperSussySettings()
        original = settings.alert_cooldown_s
        result = update_field(settings, "alert_cooldown_s", original + 60)
        assert result == original + 60
        assert settings.alert_cooldown_s == original + 60

    def test_coerces_type(self) -> None:
        """String-ish numerics are coerced by Pydantic."""
        settings = HyperSussySettings()
        result = update_field(settings, "oi_concentration_top_n", "7")
        # The registry declares this as int, Pydantic coerces from str.
        assert isinstance(result, int)
        assert result == 7

    def test_rejects_cold_field(self) -> None:
        """Fields outside the hot registry raise SettingsUpdateError."""
        settings = HyperSussySettings()
        with pytest.raises(SettingsUpdateError, match="not live-editable"):
            update_field(settings, "db_path", "/tmp/evil.db")

    def test_rejects_invalid_value(self) -> None:
        """Pydantic validation errors bubble up as SettingsUpdateError."""
        settings = HyperSussySettings()
        with pytest.raises(SettingsUpdateError):
            update_field(settings, "oi_concentration_top_n", "not-a-number")

    def test_does_not_mutate_on_validation_failure(self) -> None:
        """Failed updates leave the live settings untouched."""
        settings = HyperSussySettings()
        original = settings.oi_concentration_top_n
        with pytest.raises(SettingsUpdateError):
            update_field(settings, "oi_concentration_top_n", "garbage")
        assert settings.oi_concentration_top_n == original


class TestApplyPersistedOverrides:
    """Tests for the startup override-merge path."""

    def test_applies_hot_overrides(self) -> None:
        """Valid overrides are merged onto the live instance."""
        settings = HyperSussySettings()
        overrides = {"alert_cooldown_s": json.dumps(1800)}
        apply_persisted_overrides(settings, overrides)
        assert settings.alert_cooldown_s == 1800

    def test_skips_unknown_keys(self) -> None:
        """Unknown keys are logged and ignored, not raised."""
        settings = HyperSussySettings()
        original = settings.alert_cooldown_s
        overrides = {
            "not_a_real_field": json.dumps(99),
            "alert_cooldown_s": json.dumps(original + 30),
        }
        apply_persisted_overrides(settings, overrides)
        # The known key still applies.
        assert settings.alert_cooldown_s == original + 30

    def test_skips_cold_fields(self) -> None:
        """Persisted overrides for non-hot fields are ignored."""
        settings = HyperSussySettings()
        original_path = settings.db_path
        overrides = {"db_path": json.dumps("/tmp/hijack.db")}
        apply_persisted_overrides(settings, overrides)
        assert settings.db_path == original_path

    def test_skips_malformed_json(self) -> None:
        """Corrupt rows don't sink the startup sequence."""
        settings = HyperSussySettings()
        original = settings.alert_cooldown_s
        overrides = {"alert_cooldown_s": "{not json}"}
        apply_persisted_overrides(settings, overrides)
        assert settings.alert_cooldown_s == original

    def test_skips_invalid_value(self) -> None:
        """Values that fail validation don't sink startup."""
        settings = HyperSussySettings()
        original = settings.oi_concentration_top_n
        overrides = {"oi_concentration_top_n": json.dumps("not-a-number")}
        apply_persisted_overrides(settings, overrides)
        assert settings.oi_concentration_top_n == original


class TestHotFieldsRegistry:
    """Sanity checks on the HOT_FIELDS registry itself."""

    def test_all_fields_exist_on_settings(self) -> None:
        """Every registry entry names a real settings field."""
        settings = HyperSussySettings()
        for key in HOT_FIELDS:
            assert hasattr(settings, key), (
                f"HOT_FIELDS entry {key!r} missing on settings"
            )

    def test_all_fields_are_numeric_or_bool(self) -> None:
        """Hot fields must be scalar JSON-serialisable types.

        The ConfigRow UI only renders number and toggle inputs, and
        the API schema constrains ``value`` to ``float | int | bool``.
        Anything else in the registry would crash the serializer at
        first load.
        """
        settings = HyperSussySettings()
        for key in HOT_FIELDS:
            value = getattr(settings, key)
            assert isinstance(value, int | float | bool), (
                f"{key!r} has non-scalar type {type(value).__name__}"
            )
