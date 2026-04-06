"""Pydantic v2 response and request models for the HyperSussy API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OISnapshotItem(_Base):
    """Open interest snapshot row."""

    timestamp_ms: int
    open_interest_usd: float
    mark_price: float
    funding_rate: float


class FundingSnapshotItem(_Base):
    """Funding rate snapshot row."""

    timestamp_ms: int
    funding_rate: float
    premium: float
    mark_price: float
    oracle_price: float


class AlertItem(_Base):
    """Full alert row (from alerts table)."""

    alert_id: str
    alert_type: str
    severity: str
    coin: str
    title: str
    description: str
    timestamp_ms: int
    exchange: str
    address: str | None = None


class AlertSummaryItem(_Base):
    """Condensed alert row (by-address query returns fewer columns)."""

    alert_type: str
    severity: str
    coin: str
    title: str
    timestamp_ms: int


class TopWhaleItem(_Base):
    """Top address by trading volume."""

    address: str
    volume_usd: float


class TradeItem(_Base):
    """Individual trade row."""

    tid: int
    coin: str
    price: float
    size: float
    side: str
    timestamp_ms: int
    buyer: str
    seller: str


class TopHolderItem(_Base):
    """Address volume with market-total denominator."""

    address: str
    volume_usd: float
    total_volume: float


class TradeFlowItem(_Base):
    """Buy/sell volume bucketed by hour."""

    bucket: int
    side: str
    volume_usd: float


class TrackedAddressItem(_Base):
    """Tracked whale address row."""

    address: str
    label: str | None = None
    total_volume_usd: float
    last_active_ms: int | None = None
    source: str


class PositionItem(_Base):
    """Open position for a whale address."""

    coin: str
    size: float
    notional_usd: float
    unrealized_pnl: float
    liquidation_price: float | None = None
    mark_price: float
    timestamp_ms: int


class CoinPositionItem(_Base):
    """Current open position for a tracked address in a specific coin."""

    address: str
    coin: str
    size: float
    entry_price: float | None = None
    notional_usd: float
    unrealized_pnl: float
    leverage_value: float | None = None
    leverage_type: str | None = None
    liquidation_price: float | None = None
    mark_price: float
    margin_used: float | None = None
    timestamp_ms: int


class CandleItem(_Base):
    """OHLCV candle row."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    num_trades: int


class RuntimeIssueItem(_Base):
    """A single runtime or engine error."""

    source: str
    message: str
    timestamp_ms: int


class HealthResponse(_Base):
    """Current orchestrator health summary."""

    is_running: bool
    snapshot_count: int
    last_snapshot_ms: int | None = None
    last_alert_ms: int | None = None
    engine_errors: list[RuntimeIssueItem]
    runtime_errors: list[RuntimeIssueItem]


class AddWhaleRequest(BaseModel):
    """Request body for POST /api/whales."""

    address: str
    label: str = ""


class RealizedPnlResponse(_Base):
    """Realized PnL summary for a wallet address."""

    pnl_7d: float
    pnl_all_time: float
    fills_7d: int
    fills_all_time: int
    is_complete_7d: bool = True
    is_complete_all_time: bool = True


class FillItem(_Base):
    """A single user fill from the Hyperliquid API."""

    coin: str
    side: str
    dir: str
    px: float
    sz: float
    closed_pnl: float
    start_position: float
    oid: int
    hash: str
    time: int
    crossed: bool


class FillPageResponse(_Base):
    """Paginated fill history response."""

    fills: list[FillItem]
    next_cursor: int | None = None


class WhaleCountResponse(BaseModel):
    """Response for GET /api/whales/count."""

    count: int
