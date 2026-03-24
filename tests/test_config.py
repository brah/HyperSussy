"""Tests for configuration loading."""

from __future__ import annotations

from hypersussy.config import HyperSussySettings


class TestHyperSussySettings:
    """Tests for settings defaults and env var loading."""

    def test_defaults(self) -> None:
        """All settings have sensible defaults."""
        settings = HyperSussySettings()
        assert settings.hl_api_url == "https://api.hyperliquid.xyz"
        assert settings.log_level == "INFO"
        assert settings.watched_coins == []
        assert settings.oi_change_pct_threshold == 0.10
        assert settings.max_tracked_addresses == 200

    def test_env_override(self, monkeypatch: object) -> None:
        """Settings can be overridden via env vars."""
        import os

        os.environ["HYPERSUSSY_LOG_LEVEL"] = "DEBUG"
        os.environ["HYPERSUSSY_MAX_TRACKED_ADDRESSES"] = "500"
        try:
            settings = HyperSussySettings()
            assert settings.log_level == "DEBUG"
            assert settings.max_tracked_addresses == 500
        finally:
            del os.environ["HYPERSUSSY_LOG_LEVEL"]
            del os.environ["HYPERSUSSY_MAX_TRACKED_ADDRESSES"]

    def test_oi_windows_default(self) -> None:
        """OI change windows default to 5m, 15m, 1h."""
        settings = HyperSussySettings()
        assert settings.oi_change_windows_ms == [
            300_000,
            900_000,
            3_600_000,
        ]
