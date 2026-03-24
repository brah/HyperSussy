"""Alert feed page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader

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
    """Render the filterable alert feed page.

    Provides filter controls for severity, type, coin, and time range.
    Auto-refreshes every refresh_s seconds.

    Args:
        db_reader: Read-only SQLite reader for historical queries.
        refresh_s: Auto-refresh interval in seconds.
    """
    st.header("Alert Feed")

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        _render_filters_and_table(db_reader)
        _render_hourly_chart(db_reader)

    _live()


def _render_filters_and_table(db_reader: DashboardReader) -> None:
    """Render filter controls and the filtered alert dataframe."""
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

    # Apply filters
    if selected_severities:
        rows = [r for r in rows if r["severity"] in selected_severities]
    if selected_types:
        rows = [r for r in rows if r["alert_type"] in selected_types]
    if coin_filter.strip():
        needle = coin_filter.strip().upper()
        rows = [r for r in rows if str(r["coin"]).upper() == needle]

    if not rows:
        st.info("No alerts match the current filters.")
        return

    df = pl.DataFrame(
        [
            {
                "Time": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(int(r["timestamp_ms"]) / 1000),
                ),
                "Coin": r["coin"],
                "Type": r["alert_type"],
                "Severity": r["severity"],
                "Title": r["title"],
                "Description": r["description"],
            }
            for r in rows
        ]
    )

    st.dataframe(df, width="stretch", hide_index=True)


def _render_hourly_chart(db_reader: DashboardReader) -> None:
    """Render a bar chart of alert volume per hour over the last 24 hours."""
    now_ms = int(time.time() * 1000)
    rows = db_reader.get_alerts_all(limit=1000, since_ms=now_ms - 86_400_000)
    if not rows:
        return

    # Bucket by hour
    buckets: dict[str, int] = {}
    for row in rows:
        hour_label = time.strftime(
            "%H:00", time.localtime(int(row["timestamp_ms"]) / 1000)
        )
        buckets[hour_label] = buckets.get(hour_label, 0) + 1

    df = pl.DataFrame(
        {"Hour": list(buckets.keys()), "Alerts": list(buckets.values())}
    ).sort("Hour")

    st.subheader("Alert Volume (last 24h, by hour)")
    st.bar_chart(df, x="Hour", y="Alerts", width="stretch")
