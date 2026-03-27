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

    # HIP-3 builder-deployed perpetuals
    include_hip3: bool = True
    hip3_dex_filter: list[str] = Field(default_factory=list)

    # Database
    db_path: str = "data/hypersussy.db"

    # Rate limiting
    rate_limit_weight: int = 1200
    rate_limit_window_s: int = 60
    candle_rate_limit_weight: int = 200

    # Engine toggles
    engine_oi_concentration: bool = True
    engine_whale_tracker: bool = True
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
    oi_history_maxlen: int = 4000

    # Whale Tracker engine
    whale_volume_threshold_usd: float = 25_000_000.0
    whale_discovery_oi_pct: float = 0.15  # promote if address trades >= 15% of coin OI
    # OI-path requires this minimum position size
    whale_oi_min_notional_usd: float = 500_000.0
    whale_volume_lookback_ms: int = 3_600_000
    max_tracked_addresses: int = 200
    position_poll_interval_s: float = 150.0
    large_position_oi_pct: float = 0.20
    large_position_min_oi_usd: float = 1_500_000.0
    large_position_change_usd: float = 1_000_000.0
    whale_poll_batch_size: int = 10
    twap_active_window_multiplier: int = 3

    # Position Census — polls positions for non-whale addresses
    census_enabled: bool = True
    census_poll_interval_s: float = 300.0
    census_poll_batch_size: int = 5
    census_min_volume_usd: float = 100_000.0
    census_max_addresses: int = 500
    census_volume_lookback_ms: int = 3_600_000

    # Pre-Move engine
    pre_move_threshold_pct: float = 0.02
    pre_move_windows_ms: list[int] = Field(
        default_factory=lambda: [60_000, 300_000, 900_000]
    )
    pre_move_lookback_ms: int = 900_000
    pre_move_min_notional_usd: float = 500_000.0
    pre_move_top_n: int = 5
    pre_move_cooldown_ms: int = 3_600_000
    pre_move_price_maxlen: int = 10_000
    pre_move_trade_maxlen: int = 50_000

    # Funding Anomaly engine
    funding_zscore_threshold: float = 3.0
    funding_abs_threshold: float = 0.001
    funding_rolling_window: int = 168  # hours
    funding_min_samples: int = 24

    # Liquidation Risk engine
    liquidation_distance_threshold: float = 0.05
    liquidation_max_tracked: int = 50

    # Alert system
    alert_cooldown_s: int = 3600
    alert_max_per_minute: int = 10

    # WebSocket throttling
    ws_connect_delay_s: float = 2.5
    ws_subscribe_delay_s: float = 0.05

    # Polling intervals
    meta_poll_interval_s: float = 10.0
    engine_tick_interval_s: float = 10.0
    asset_list_refresh_s: float = 300.0

    # Logging
    log_level: str = "INFO"
