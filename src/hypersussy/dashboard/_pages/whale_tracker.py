"""Whale tracker page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import plotly.graph_objects as go
import streamlit as st

from hypersussy.dashboard.actions import DashboardActions
from hypersussy.dashboard.components import (
    render_alert_feed,
    render_empty_state,
    render_page_header,
    render_section_header,
)
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import (
    CHART_FONT_COLOR,
    CHART_GREY,
    CHART_GRID,
    CHART_PAPER_BG,
    CHART_PLOT_BG,
    CHART_TEAL,
)
from hypersussy.dashboard.navigation import normalize_wallet_address
from hypersussy.dashboard.view_models import (
    build_alert_feed_items,
    build_positions_table,
    build_top_trader_views,
    build_top_traders_df,
    build_tracked_address_views,
    coerce_select_int,
)

_HOURS_OPTIONS = [1, 4, 24]
_COL_VOLUME = "Volume (USD)"


def render_whale_tracker(
    db_reader: DashboardReader,
    actions: DashboardActions,
    refresh_s: int,
) -> None:
    """Render the whale tracking page."""
    render_page_header(
        "Whale Tracker",
        "Inspect tracked addresses, drill into their open positions and alert history, and compare them with the top traders by coin.",
    )

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        _render_address_panel(db_reader, actions)
        st.divider()
        _render_top_traders(db_reader)

    _live()


def _render_address_panel(
    db_reader: DashboardReader,
    actions: DashboardActions,
) -> None:
    """Two-column layout: address list and selected address detail."""
    with st.expander("Add whale manually", expanded=False):
        with st.form("add_whale_form", clear_on_submit=True):
            new_addr = st.text_input("Address (0x...)")
            new_label = st.text_input("Label (optional)", value="")
            submitted = st.form_submit_button("Add")
            if submitted:
                addr = normalize_wallet_address(new_addr)
                if addr is None:
                    st.error("Address must be a 42-character 0x hex string.")
                else:
                    actions.add_tracked_address(addr, new_label.strip() or "MANUAL")
                    st.rerun()

    addresses = build_tracked_address_views(db_reader.get_tracked_addresses(limit=100))
    if not addresses:
        render_empty_state(
            "No tracked whale addresses yet. Threshold: $5M volume or 5% of coin OI in 1h."
        )
        return

    col_list, col_detail = st.columns([1, 2])

    with col_list:
        render_section_header("Tracked Whales", "Highest-volume tracked addresses.")
        selected_idx = st.radio(
            "Select address",
            options=range(len(addresses)),
            format_func=lambda index: addresses[index].radio_label,
            label_visibility="collapsed",
        )

    selected = addresses[selected_idx]
    with col_detail:
        render_section_header(selected.label, selected.address)

        action_cols = st.columns([1, 1, 2])
        with action_cols[0]:
            if st.button("View wallet", key=f"view_{selected.address}"):
                st.query_params["page"] = "wallet"
                st.query_params["address"] = selected.address
                st.rerun()
        with action_cols[1]:
            if st.button("Remove", key=f"remove_{selected.address}"):
                actions.remove_tracked_address(selected.address)
                st.rerun()

        meta_parts = [f"Source: {selected.source or 'tracked'}"]
        if selected.last_active_ms is not None:
            meta_parts.append(
                "Last active: "
                + time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(selected.last_active_ms / 1000),
                )
            )
        st.caption(" | ".join(meta_parts))

        tab_pos, tab_alerts = st.tabs(["Positions", "Alert History"])
        with tab_pos:
            positions = db_reader.get_whale_positions(selected.address)
            if not positions:
                render_empty_state("No open positions found.")
            else:
                st.dataframe(
                    build_positions_table(
                        positions,
                        db_reader.get_latest_oi_per_coin(),
                    ),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Notional (USD)": st.column_config.NumberColumn(
                            format="$%,.0f"
                        ),
                        "Unr. PnL": st.column_config.NumberColumn(format="$%+,.0f"),
                    },
                )

        with tab_alerts:
            render_alert_feed(
                build_alert_feed_items(db_reader.get_alerts_by_address(selected.address)),
                empty_message="No alerts triggered by this address yet.",
            )


def _render_top_traders(db_reader: DashboardReader) -> None:
    """Render top traders by volume for a selected coin."""
    render_section_header(
        "Top Traders by Coin",
        "Compare tracked whales against the heaviest recent traders for a selected market.",
    )
    coins = db_reader.get_distinct_coins()
    if not coins:
        render_empty_state("No trade data available yet.")
        return

    col_coin, col_hours = st.columns(2)
    with col_coin:
        selected_coin = st.selectbox("Coin", options=coins, key="top_traders_coin")
    with col_hours:
        hours = st.selectbox(
            "Lookback",
            options=_HOURS_OPTIONS,
            format_func=lambda value: f"{value}h",
            key="top_traders_hours",
        )

    if selected_coin is None:
        return

    lookback_hours = coerce_select_int(hours, default=1)
    rows = db_reader.get_top_whales(str(selected_coin), hours=lookback_hours)
    if not rows:
        render_empty_state(f"No trades for {selected_coin} in the last {lookback_hours}h.")
        return

    tracked_set = {
        str(row["address"]) for row in db_reader.get_tracked_addresses(limit=1000)
    }
    top_rows = build_top_trader_views(rows, tracked_set)

    sorted_rows = sorted(top_rows, key=lambda row: row.volume_usd)
    fig = go.Figure(
        go.Bar(
            x=[row.volume_usd for row in sorted_rows],
            y=[row.short_address for row in sorted_rows],
            orientation="h",
            marker_color=[
                CHART_TEAL if row.tracked else CHART_GREY for row in sorted_rows
            ],
            hovertext=[
                f"<b>{row.address}</b><br>Volume: ${row.volume_usd:,.0f}"
                for row in sorted_rows
            ],
            hoverinfo="text",
        )
    )
    fig.update_layout(
        xaxis_title=_COL_VOLUME,
        yaxis_title=None,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        height=320,
        plot_bgcolor=CHART_PLOT_BG,
        paper_bgcolor=CHART_PAPER_BG,
        font_color=CHART_FONT_COLOR,
        xaxis={
            "tickprefix": "$",
            "tickformat": ",.0f",
            "gridcolor": CHART_GRID,
        },
        yaxis={"gridcolor": CHART_GRID},
    )
    st.plotly_chart(fig, width="stretch")

    st.dataframe(
        build_top_traders_df(top_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Volume (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "% of Top 10": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    selected_wallet = st.selectbox(
        "Inspect a top trader wallet",
        options=[row.address for row in top_rows],
        format_func=lambda address: address,
        key="top_trader_wallet",
    )
    if st.button("Open selected wallet", key="open_top_trader_wallet"):
        st.query_params["page"] = "wallet"
        st.query_params["address"] = selected_wallet
        st.rerun()
