"""Typed dashboard view models and row builders."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import polars as pl

from hypersussy.dashboard.formatting import (
    build_positions_df,
    format_price,
    sort_alerts_by_severity,
)
from hypersussy.dashboard.navigation import short_wallet_label
from hypersussy.dashboard.state import LiveSnapshot, RuntimeHealth


@dataclass(frozen=True, slots=True)
class MetricCardData:
    """Content for a single top-line dashboard metric."""

    label: str
    value: str | int | float
    help_text: str | None = None


@dataclass(frozen=True, slots=True)
class AlertFeedItem:
    """Structured alert item for feed rendering."""

    severity: str
    coin: str
    title: str
    timestamp_ms: int
    alert_type: str = ""
    address: str | None = None


@dataclass(frozen=True, slots=True)
class TrackedAddressView:
    """Presentation-friendly tracked address summary."""

    address: str
    label: str
    total_volume_usd: float
    last_active_ms: int | None
    source: str

    @property
    def radio_label(self) -> str:
        """Compact label suitable for the whale sidebar chooser."""
        return f"{self.label} - ${self.total_volume_usd:,.0f}"


@dataclass(frozen=True, slots=True)
class TopTraderView:
    """Presentation-friendly top trader row."""

    rank: int
    address: str
    short_address: str
    volume_usd: float
    pct_of_top_ten: float
    tracked: bool


def build_market_table(snapshots: dict[str, LiveSnapshot]) -> pl.DataFrame:
    """Convert live snapshots into a sorted market table."""
    rows = [
        {
            "Coin": snapshot.coin,
            "Mark Price": format_price(snapshot.mark_price),
            "OI (USD)": snapshot.open_interest_usd,
            "Funding Rate": snapshot.funding_rate,
            "Premium": snapshot.premium,
            "24h Volume": snapshot.day_volume_usd,
            "Updated": time.strftime(
                "%H:%M:%S", time.localtime(snapshot.timestamp_ms / 1000)
            ),
        }
        for snapshot in sorted(
            snapshots.values(),
            key=lambda item: item.open_interest_usd,
            reverse=True,
        )
        if snapshot.mark_price > 0
        and (snapshot.open_interest_usd > 0 or snapshot.day_volume_usd > 0)
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def build_alert_feed_items(rows: list[dict[str, object]]) -> list[AlertFeedItem]:
    """Convert raw alert rows into sorted alert feed items."""
    items = [
        AlertFeedItem(
            severity=str(row["severity"]),
            coin=str(row["coin"]),
            title=str(row["title"]),
            timestamp_ms=int(row["timestamp_ms"]),
            alert_type=str(row.get("alert_type") or ""),
            address=str(row["address"]) if row.get("address") else None,
        )
        for row in sort_alerts_by_severity(rows)
    ]
    return items


def build_alert_counts_df(counts: dict[str, int]) -> pl.DataFrame:
    """Convert alert counts into a chart-ready dataframe."""
    if not counts:
        return pl.DataFrame(schema={"Type": pl.Utf8, "Count": pl.Int64})
    return pl.DataFrame(
        {"Type": list(counts.keys()), "Count": list(counts.values())}
    ).sort("Count", descending=True)


def build_tracked_address_views(
    rows: list[dict[str, object]],
) -> list[TrackedAddressView]:
    """Convert tracked-address query rows into typed views."""
    views: list[TrackedAddressView] = []
    for row in rows:
        last_active_raw = row.get("last_active_ms")
        views.append(
            TrackedAddressView(
                address=str(row["address"]),
                label=str(row["label"] or "WHALE"),
                total_volume_usd=float(row["total_volume_usd"] or 0.0),
                last_active_ms=int(last_active_raw) if last_active_raw else None,
                source=str(row["source"] or ""),
            )
        )
    return views


def build_trade_history_df(
    rows: list[dict[str, object]],
    address: str,
) -> pl.DataFrame:
    """Convert raw trade rows into a readable trade-history table."""
    formatted_rows = [
        {
            "Time": time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(int(row["timestamp_ms"]) / 1000),
            ),
            "Coin": str(row["coin"]),
            "Side": "BUY" if row["side"] == "B" else "SELL",
            "Size": float(row["size"]),
            "Price": format_price(float(row["price"])),
            "Notional": float(row["price"]) * float(row["size"]),
            "Counterparty": (
                str(row["seller"])
                if str(row["buyer"]) == address
                else str(row["buyer"])
            ),
        }
        for row in rows
    ]
    return (
        pl.DataFrame(formatted_rows)
        if formatted_rows
        else pl.DataFrame(
            schema={
                "Time": pl.Utf8,
                "Coin": pl.Utf8,
                "Side": pl.Utf8,
                "Size": pl.Float64,
                "Price": pl.Utf8,
                "Notional": pl.Float64,
                "Counterparty": pl.Utf8,
            }
        )
    )


def build_top_trader_views(
    rows: list[dict[str, object]],
    tracked_addresses: set[str],
) -> list[TopTraderView]:
    """Convert ranked top-trader rows into typed views."""
    top_ten = rows[:10]
    total_volume = sum(float(row["volume_usd"]) for row in top_ten) or 1.0
    return [
        TopTraderView(
            rank=index + 1,
            address=str(row["address"]),
            short_address=short_wallet_label(str(row["address"]), width=8),
            volume_usd=float(row["volume_usd"]),
            pct_of_top_ten=float(row["volume_usd"]) / total_volume * 100,
            tracked=str(row["address"]) in tracked_addresses,
        )
        for index, row in enumerate(top_ten)
    ]


def build_top_traders_df(rows: list[TopTraderView]) -> pl.DataFrame:
    """Convert top-trader views into a table dataframe."""
    return (
        pl.DataFrame(
            [
                {
                    "Rank": row.rank,
                    "Address": row.address,
                    "Volume (USD)": row.volume_usd,
                    "% of Top 10": row.pct_of_top_ten,
                    "Tracked": "Yes" if row.tracked else "",
                }
                for row in rows
            ]
        )
        if rows
        else pl.DataFrame(
            schema={
                "Rank": pl.Int64,
                "Address": pl.Utf8,
                "Volume (USD)": pl.Float64,
                "% of Top 10": pl.Float64,
                "Tracked": pl.Utf8,
            }
        )
    )


def format_runtime_freshness(
    health: RuntimeHealth,
    now_ms: int,
    stale_after_ms: int,
) -> str:
    """Return a short freshness summary for the current runtime health."""
    if health.last_snapshot_ms is None:
        return "Waiting for first market snapshot."
    age_ms = max(0, now_ms - health.last_snapshot_ms)
    age_s = age_ms // 1000
    if age_ms > stale_after_ms:
        return f"Latest market snapshot is stale ({age_s}s old)."
    return f"Latest market snapshot received {age_s}s ago."


def build_positions_table(
    positions: list[dict[str, object]],
    oi_by_coin: dict[str, float],
) -> pl.DataFrame:
    """Build the standard positions table dataframe."""
    return build_positions_df(positions, oi_by_coin)


def coerce_select_int(value: Any, default: int) -> int:
    """Safely coerce selectbox/slider values to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
