"""Live market overview page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import format_price, severity_color
from hypersussy.dashboard.state import SharedState

_COL_24H_VOL = "24h Volume"


def _format_usd(value: float) -> str:
    """Format a USD value with B/M suffix.

    Args:
        value: Dollar amount.

    Returns:
        Human-readable string, e.g. "1.23B" or "456M".
    """
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
    """Render the live market overview page.

    Displays a status banner, metric summary row, live market table
    sorted by open interest, and a compact recent-alert strip.
    Auto-refreshes every refresh_s seconds.

    Args:
        state: Thread-safe shared state from the orchestrator thread.
        db_reader: Read-only SQLite reader for historical queries.
        refresh_s: Auto-refresh interval in seconds.
    """
    st.header("Overview")

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        _render_status_banner(state)
        _render_metrics(state, db_reader)
        _render_market_table(state)
        _render_recent_alerts(state)

    _live()


def _render_status_banner(state: SharedState) -> None:
    """Show orchestrator running status."""
    if state.is_running:
        st.success("Orchestrator running — data is live")
    else:
        st.warning(
            "Orchestrator not running. Start with `hypersussy --streamlit`."
        )


def _render_metrics(state: SharedState, db_reader: DashboardReader) -> None:
    """Display top-level metric cards."""
    snapshots = state.get_snapshots()
    now_ms = int(time.time() * 1000)
    since_1h_ms = now_ms - 3_600_000

    total_oi = sum(s.open_interest_usd for s in snapshots.values())
    total_vol = sum(s.day_volume_usd for s in snapshots.values())
    alert_counts = db_reader.get_alert_counts_by_type(since_ms=since_1h_ms)
    total_alerts_1h = sum(alert_counts.values())
    tracked = len(db_reader.get_tracked_addresses(limit=1000))

    cols = st.columns(5)
    cols[0].metric("Total OI", _format_usd(total_oi))
    cols[1].metric(_COL_24H_VOL, _format_usd(total_vol))
    cols[2].metric("Coins Tracked", len(snapshots))
    cols[3].metric("Alerts (1h)", total_alerts_1h)
    cols[4].metric("Whales Tracked", tracked)


def _render_market_table(state: SharedState) -> None:
    """Render the live market data table sorted by OI descending.

    Only shows coins with a non-zero mark price (active markets).
    """
    snapshots = state.get_snapshots()
    if not snapshots:
        st.info("Waiting for first market data poll (~10s)...")
        return

    rows = [
        {
            "Coin": s.coin,
            "Mark Price": format_price(s.mark_price),
            "OI (USD)": s.open_interest_usd,
            "Funding Rate": s.funding_rate,
            "Premium": s.premium,
            _COL_24H_VOL: s.day_volume_usd,
        }
        for s in sorted(
            snapshots.values(),
            key=lambda x: x.open_interest_usd,
            reverse=True,
        )
        if s.mark_price > 0 and (s.open_interest_usd > 0 or s.day_volume_usd > 0)
    ]

    if not rows:
        st.info("Waiting for first market data poll (~10s)...")
        return

    df = pl.DataFrame(rows)

    st.subheader("Live Market")
    st.dataframe(
        df,
        width="stretch",
        column_config={
            "OI (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "Funding Rate": st.column_config.NumberColumn(format="%+.4f%%"),
            "Premium": st.column_config.NumberColumn(format="%.4f%%"),
            _COL_24H_VOL: st.column_config.NumberColumn(format="$%,.0f"),
        },
        hide_index=True,
    )


def _render_recent_alerts(state: SharedState) -> None:
    """Display the 10 most recent alerts as a condensed list."""
    alerts = state.get_recent_alerts(limit=10)
    if not alerts:
        return

    st.subheader("Recent Alerts")
    for alert in alerts:
        severity = alert.severity
        color = severity_color(severity)

        ts = time.strftime(
            "%H:%M:%S", time.localtime(alert.timestamp_ms / 1000)
        )
        st.markdown(
            f'<span style="color:{color}">**[{severity.upper()}]**</span> '
            f"`{alert.coin}` — **{alert.title}** _{ts}_",
            unsafe_allow_html=True,
        )
