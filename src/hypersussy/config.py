"""Configuration via pydantic-settings with .env support."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class HyperSussySettings(BaseSettings):
    """All configurable thresholds and connection parameters.

    Every field is overridable via environment variable with
    ``HYPERSUSSY_`` prefix (e.g. ``HYPERSUSSY_LOG_LEVEL=DEBUG``).
    """

    model_config = {"env_prefix": "HYPERSUSSY_"}

    # Exchange
    hl_api_url: str = "https://api.hyperliquid.xyz"
    hl_ws_url: str = "wss://api.hyperliquid.xyz/ws"

    # Coins: empty list = all listed perps (fetched dynamically)
    watched_coins: list[str] = Field(default_factory=list)

    # Database
    db_path: str = "data/hypersussy.db"

    # Rate limiting
    rate_limit_weight: int = 1200
    rate_limit_window_s: int = 60

    # Engine toggles
    engine_oi_concentration: bool = True
    engine_whale_tracker: bool = True
    engine_twap_detector: bool = True
    engine_pre_move: bool = True
    engine_funding_anomaly: bool = True
    engine_liquidation_risk: bool = True

    # OI Concentration engine
    oi_change_pct_threshold: float = 0.10
    oi_change_windows_ms: list[int] = Field(
        default_factory=lambda: [300_000, 900_000, 3_600_000]
    )
    oi_concentration_top_n: int = 5
    oi_concentration_threshold: float = 0.20
    oi_min_usd: float = 100_000.0

    # Whale Tracker engine
    whale_volume_threshold_usd: float = 5_000_000.0
    whale_volume_lookback_ms: int = 3_600_000
    max_tracked_addresses: int = 200
    position_poll_interval_s: float = 30.0
    large_position_oi_pct: float = 0.20
    large_position_change_usd: float = 1_000_000.0

    # TWAP Detector engine
    twap_min_fills: int = 10
    twap_max_time_cv: float = 0.5
    twap_max_size_cv: float = 0.5
    twap_window_ms: int = 1_800_000
    twap_min_notional_usd: float = 100_000.0

    # Pre-Move engine
    pre_move_threshold_pct: float = 0.02
    pre_move_windows_ms: list[int] = Field(
        default_factory=lambda: [60_000, 300_000, 900_000]
    )
    pre_move_lookback_ms: int = 900_000
    pre_move_min_notional_usd: float = 500_000.0
    pre_move_top_n: int = 5
    pre_move_cooldown_ms: int = 3_600_000

    # Funding Anomaly engine
    funding_zscore_threshold: float = 3.0
    funding_abs_threshold: float = 0.001
    funding_rolling_window: int = 168  # hours

    # Liquidation Risk engine
    liquidation_distance_threshold: float = 0.05

    # Alert system
    alert_cooldown_s: int = 3600
    alert_max_per_minute: int = 10

    # WebSocket throttling
    ws_connect_delay_s: float = 2.5
    ws_subscribe_delay_s: float = 0.05

    # Polling intervals
    meta_poll_interval_s: float = 10.0
    asset_list_refresh_s: float = 300.0

    # Logging
    log_level: str = "INFO"
