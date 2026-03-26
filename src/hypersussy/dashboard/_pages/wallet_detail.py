"""Wallet detail page for the HyperSussy dashboard."""

from __future__ import annotations

import streamlit as st

from hypersussy.dashboard.components import (
    render_alert_feed,
    render_empty_state,
    render_page_header,
    render_positions_table,
    render_section_header,
)
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.navigation import normalize_wallet_address
from hypersussy.dashboard.view_models import (
    build_alert_feed_items,
    build_positions_table,
    build_trade_history_df,
    coerce_select_int,
)


def render_wallet_detail(db_reader: DashboardReader, refresh_s: int) -> None:
    """Render a deep-dive view for a single wallet address."""
    query_address = st.query_params.get("address", "")
    address = normalize_wallet_address(query_address)

    if address is None:
        st.warning("Invalid or missing wallet address.")
        if st.button("Back to dashboard"):
            st.query_params.clear()
            st.rerun()
        return

    if st.button("Back"):
        st.query_params.clear()
        st.rerun()

    render_page_header(
        f"Wallet ...{address[-10:]}",
        "Inspect the latest open positions, recent trade history, and alert activity for a tracked address.",
    )
    st.caption(address)

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        tab_pos, tab_trades, tab_alerts = st.tabs(
            ["Positions", "Trade History", "Alerts"]
        )
        with tab_pos:
            _render_positions(db_reader, address)
        with tab_trades:
            _render_trades(db_reader, address)
        with tab_alerts:
            _render_alerts(db_reader, address)

    _live()


def _render_positions(db_reader: DashboardReader, address: str) -> None:
    """Render latest positions for the wallet."""
    positions = db_reader.get_whale_positions(address)
    if not positions:
        render_empty_state("No open positions found.")
        return

    render_positions_table(
        build_positions_table(positions, db_reader.get_latest_oi_per_coin())
    )


def _render_trades(db_reader: DashboardReader, address: str) -> None:
    """Render recent trade history for the wallet."""
    render_section_header(
        "Trade History",
        "Recent fills involving this address as either buyer or seller.",
    )
    hours = st.select_slider(
        "Lookback",
        options=[1, 4, 24, 48, 168],
        value=24,
        format_func=lambda value: f"{value}h",
        key="wallet_trade_hours",
    )

    lookback_hours = coerce_select_int(hours, default=24)
    rows = db_reader.get_trades_by_address(address, hours=lookback_hours)
    if not rows:
        render_empty_state(f"No trades in the last {lookback_hours}h.")
        return

    st.dataframe(
        build_trade_history_df(rows, address),
        width="stretch",
        hide_index=True,
        column_config={
            "Notional": st.column_config.NumberColumn(format="$%,.0f"),
        },
    )


def _render_alerts(db_reader: DashboardReader, address: str) -> None:
    """Render alert history for the wallet."""
    render_alert_feed(
        build_alert_feed_items(db_reader.get_alerts_by_address(address, limit=50)),
        empty_message="No alerts triggered by this address yet.",
    )
