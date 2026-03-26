"""Live market overview page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import streamlit as st

from hypersussy.dashboard.components import (
    render_alert_feed,
    render_empty_state,
    render_metric_cards,
    render_page_header,
    render_runtime_issues,
    render_section_header,
    render_status_banner,
)
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.state import LiveSnapshot, SharedState
from hypersussy.dashboard.view_models import (
    AlertFeedItem,
    MetricCardData,
    build_market_table,
    format_runtime_freshness,
)


def _format_usd(value: float) -> str:
    """Format a USD value with B/M suffix."""
    if value >= 1e9:
        return f"{value / 1e9:.2f}B"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    return f"{value:,.0f}"


def render_overview(
    state: SharedState,
    db_reader: DashboardReader,
    refresh_s: int,
) -> None:
    """Render the live market overview page."""
    render_page_header(
        "Overview",
        "Live market coverage, alert velocity, and runner health for the current monitoring session.",
    )

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        now_ms = int(time.time() * 1000)
        snapshots = state.get_snapshots()
        health = state.get_runtime_health()
        freshness = format_runtime_freshness(
            health,
            now_ms=now_ms,
            stale_after_ms=max(refresh_s * 3_000, 30_000),
        )
        render_status_banner(health, freshness)
        render_runtime_issues(health)
        _render_metrics(snapshots, db_reader, now_ms)
        _render_market_table(snapshots, health.last_snapshot_ms)
        _render_recent_alerts(state)

    _live()


def _render_metrics(
    snapshots: dict[str, LiveSnapshot],
    db_reader: DashboardReader,
    now_ms: int,
) -> None:
    """Display top-level metric cards."""
    since_1h_ms = now_ms - 3_600_000
    total_oi = sum(snapshot.open_interest_usd for snapshot in snapshots.values())
    total_vol = sum(snapshot.day_volume_usd for snapshot in snapshots.values())
    total_alerts_1h = sum(db_reader.get_alert_counts_by_type(since_ms=since_1h_ms).values())
    tracked = db_reader.get_tracked_address_count()

    render_metric_cards(
        [
            MetricCardData("Total OI", _format_usd(total_oi)),
            MetricCardData("24h Volume", _format_usd(total_vol)),
            MetricCardData("Coins Tracked", len(snapshots)),
            MetricCardData("Alerts (1h)", total_alerts_1h),
            MetricCardData("Whales Tracked", tracked),
        ]
    )


def _render_market_table(
    snapshots: dict[str, LiveSnapshot],
    last_snapshot_ms: int | None,
) -> None:
    """Render the live market data table sorted by OI descending."""
    market_df = build_market_table(snapshots)
    render_section_header(
        "Live Market",
        (
            f"Latest update at {time.strftime('%H:%M:%S', time.localtime(last_snapshot_ms / 1000))}."
            if last_snapshot_ms is not None
            else "Waiting for the first bulk snapshot from the monitor."
        ),
    )
    if market_df.is_empty():
        render_empty_state("Waiting for first market data poll (~10s)...")
        return

    st.dataframe(
        market_df,
        width="stretch",
        column_config={
            "OI (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "Funding Rate": st.column_config.NumberColumn(format="%+.4f%%"),
            "Premium": st.column_config.NumberColumn(format="%.4f%%"),
            "24h Volume": st.column_config.NumberColumn(format="$%,.0f"),
        },
        hide_index=True,
    )


def _render_recent_alerts(state: SharedState) -> None:
    """Display the 10 most recent alerts."""
    render_section_header("Recent Alerts", "Newest live alerts received by the dashboard.")
    alerts = [
        AlertFeedItem(
            severity=alert.severity,
            coin=alert.coin,
            title=alert.title,
            timestamp_ms=alert.timestamp_ms,
            alert_type=alert.alert_type,
            address=str(alert.metadata.get("address"))
            if alert.metadata.get("address")
            else None,
        )
        for alert in state.get_recent_alerts(limit=10)
    ]
    render_alert_feed(alerts, empty_message="No live alerts have been received yet.")
