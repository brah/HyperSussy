"""Alert feed page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import polars as pl
import streamlit as st

from hypersussy.dashboard.components import (
    render_alert_feed,
    render_page_header,
    render_section_header,
)
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.view_models import build_alert_counts_df, build_alert_feed_items

_ALL_SEVERITIES = ["critical", "high", "medium", "low"]
_ALL_TYPES = [
    "oi_concentration",
    "whale_position",
    "whale_position_change",
    "twap_detected",
    "pre_move",
    "funding_anomaly",
    "liquidation_risk",
]


def render_alerts(
    db_reader: DashboardReader,
    refresh_s: int,
) -> None:
    """Render the filterable alert feed page."""
    render_page_header(
        "Alert Feed",
        "Filter recent alerts by severity, engine type, coin, and recency without leaving the live dashboard.",
    )

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        _render_filters_and_feed(db_reader)
        _render_hourly_chart(db_reader)

    _live()


def _render_filters_and_feed(db_reader: DashboardReader) -> None:
    """Render filter controls and the alert feed."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        selected_severities = st.multiselect(
            "Severity",
            options=_ALL_SEVERITIES,
            default=_ALL_SEVERITIES,
        )
    with col2:
        selected_types = st.multiselect(
            "Alert Type",
            options=_ALL_TYPES,
            default=_ALL_TYPES,
        )
    with col3:
        coin_filter = st.text_input("Coin", placeholder="e.g. BTC")
    with col4:
        hours_back = st.slider("Hours back", min_value=1, max_value=168, value=24)

    now_ms = int(time.time() * 1000)
    since_ms = now_ms - hours_back * 3_600_000
    rows = db_reader.get_alerts_all(limit=500, since_ms=since_ms)

    if selected_severities:
        rows = [row for row in rows if row["severity"] in selected_severities]
    if selected_types:
        rows = [row for row in rows if row["alert_type"] in selected_types]
    if coin_filter.strip():
        needle = coin_filter.strip().upper()
        rows = [row for row in rows if str(row["coin"]).upper() == needle]

    render_section_header(
        "Matching Alerts",
        f"Showing up to 500 alerts from the last {hours_back}h after filters are applied.",
    )
    render_alert_feed(
        build_alert_feed_items(rows),
        empty_message="No alerts match the current filters.",
    )

    counts = db_reader.get_alert_counts_by_type(since_ms=since_ms)
    counts_df = build_alert_counts_df(counts)
    with st.expander("Alert counts by type", expanded=False):
        if counts_df.is_empty():
            st.info("No alert activity in the selected lookback window.")
        else:
            st.bar_chart(counts_df, x="Type", y="Count", width="stretch")


def _render_hourly_chart(db_reader: DashboardReader) -> None:
    """Render a bar chart of alert volume per hour over the last 24 hours."""
    now_ms = int(time.time() * 1000)
    rows = db_reader.get_alerts_all(limit=1000, since_ms=now_ms - 86_400_000)
    if not rows:
        return

    buckets: dict[str, int] = {}
    for row in rows:
        hour_label = time.strftime(
            "%H:00", time.localtime(int(row["timestamp_ms"]) / 1000)
        )
        buckets[hour_label] = buckets.get(hour_label, 0) + 1

    render_section_header(
        "Alert Volume (last 24h)",
        "A quick scan of when alert activity clustered during the last day.",
    )
    st.bar_chart(
        pl.DataFrame(
            {"Hour": list(buckets.keys()), "Alerts": list(buckets.values())}
        ).sort("Hour"),
        x="Hour",
        y="Alerts",
        width="stretch",
    )
