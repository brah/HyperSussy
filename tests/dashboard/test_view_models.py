"""Tests for dashboard view-model builders."""

from __future__ import annotations

from hypersussy.dashboard.view_models import (
    build_alert_feed_items,
    build_top_trader_views,
    build_trade_history_df,
    format_runtime_freshness,
)
from hypersussy.dashboard.state import RuntimeHealth, RuntimeIssue


def test_build_alert_feed_items_sorts_by_severity_then_recency() -> None:
    """Alert items are ordered for feed readability."""
    items = build_alert_feed_items(
        [
            {
                "severity": "low",
                "coin": "BTC",
                "title": "Low",
                "timestamp_ms": 1000,
                "alert_type": "funding_anomaly",
            },
            {
                "severity": "critical",
                "coin": "ETH",
                "title": "Critical",
                "timestamp_ms": 500,
                "alert_type": "liquidation_risk",
            },
        ]
    )
    assert [item.title for item in items] == ["Critical", "Low"]


def test_build_trade_history_df_adds_counterparty_and_notional() -> None:
    """Trade history rows are converted into a readable dataframe."""
    df = build_trade_history_df(
        [
            {
                "timestamp_ms": 1_000,
                "coin": "BTC",
                "side": "B",
                "size": 0.5,
                "price": 50_000.0,
                "buyer": "addr-buyer",
                "seller": "addr-seller",
            }
        ],
        "addr-buyer",
    )
    assert df.to_dicts()[0]["Counterparty"] == "addr-seller"
    assert df.to_dicts()[0]["Notional"] == 25_000.0


def test_build_top_trader_views_marks_tracked_addresses() -> None:
    """Tracked addresses are flagged in top-trader view rows."""
    rows = build_top_trader_views(
        [
            {"address": "addr1", "volume_usd": 100.0},
            {"address": "addr2", "volume_usd": 50.0},
        ],
        {"addr2"},
    )
    assert rows[0].tracked is False
    assert rows[1].tracked is True


def test_format_runtime_freshness_reports_stale_data() -> None:
    """Freshness helper warns when the latest snapshot is stale."""
    health = RuntimeHealth(
        is_running=True,
        snapshot_count=1,
        last_snapshot_ms=1_000,
        last_alert_ms=None,
        engine_errors=(RuntimeIssue("engine", "err", 1_500),),
        runtime_errors=(),
    )
    assert "stale" in format_runtime_freshness(health, now_ms=40_000, stale_after_ms=5_000)
