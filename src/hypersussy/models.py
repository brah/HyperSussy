"""Domain models for HyperSussy monitoring system.

All models are frozen dataclasses (immutable). Numeric values stored as
float (converted from HL API string representations). Timestamps are
int milliseconds matching the API convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    """Point-in-time snapshot of a perpetual asset's market state."""

    coin: str
    timestamp_ms: int
    open_interest: float
    open_interest_usd: float
    mark_price: float
    oracle_price: float
    funding_rate: float
    premium: float
    day_volume_usd: float
    mid_price: float | None = None


@dataclass(frozen=True, slots=True)
class Trade:
    """A single executed trade (fill)."""

    coin: str
    price: float
    size: float
    side: str  # "B" (buy) or "A" (sell/ask)
    timestamp_ms: int
    buyer: str  # 0x address
    seller: str  # 0x address
    tx_hash: str
    tid: int
    exchange: str = "hyperliquid"


@dataclass(frozen=True, slots=True)
class Position:
    """A user's open position on a perpetual asset."""

    coin: str
    address: str
    size: float  # signed: positive=long, negative=short
    entry_price: float
    mark_price: float
    liquidation_price: float | None
    unrealized_pnl: float
    margin_used: float
    leverage_value: int
    leverage_type: str  # "cross" | "isolated"
    notional_usd: float
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class L2Book:
    """Order book snapshot with bid/ask levels."""

    coin: str
    timestamp_ms: int
    bids: tuple[tuple[float, float], ...]  # (price, size)
    asks: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class CandleBar:
    """OHLCV candle data for a single interval."""

    coin: str
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    num_trades: int
    interval: str


@dataclass(frozen=True, slots=True)
class FundingRate:
    """A single funding rate entry."""

    coin: str
    timestamp_ms: int
    funding_rate: float
    premium: float


class TwapFillEntry(TypedDict):
    """A single fill within a TWAP slice from the HL API."""

    coin: str
    side: str  # "B" (buy) or "A" (sell/ask)
    px: str
    sz: str
    time: int
    tid: int


class TwapSliceFill(TypedDict):
    """Top-level TWAP slice fill from the HL API."""

    fill: TwapFillEntry
    twapId: int


@dataclass(frozen=True, slots=True)
class Alert:
    """A generated alert from a detection engine."""

    alert_id: str
    alert_type: str
    severity: str  # "low" | "medium" | "high" | "critical"
    coin: str
    title: str
    description: str
    timestamp_ms: int
    # ``int`` sits alongside ``float`` so integer-valued metadata
    # (window_ms, sample_count, twap_id) can stay integers through
    # serialisation rather than being cast to float at the producer
    # site. JSON serialisers accept both identically.
    metadata: dict[str, float | int | str | list[str]] = field(default_factory=dict)
    exchange: str = "hyperliquid"
