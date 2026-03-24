"""Whale tracker page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader


def render_whale_tracker(db_reader: DashboardReader) -> None:
    """Render the whale tracking page.

    Displays tracked whale addresses with their discovery label, a
    drill-down into positions and alert history for a selected address,
    and top traders by coin over the last hour.

    Args:
        db_reader: Read-only SQLite reader.
    """
    st.header("Whale Tracker")
    _render_address_panel(db_reader)
    st.divider()
    _render_top_traders(db_reader)


def _render_address_panel(db_reader: DashboardReader) -> None:
    """Two-column layout: address list and selected address detail."""
    addresses = db_reader.get_tracked_addresses(limit=100)

    if not addresses:
        st.info("No tracked whale addresses yet. Threshold: $5M volume in 1h.")
        return

    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.subheader("Tracked Whales")
        addr_labels = [
            f"{row['label'] or 'WHALE'} — ${row['total_volume_usd']:>,.0f}"
            for row in addresses
        ]
        selected_idx = st.radio(
            "Select address",
            options=range(len(addresses)),
            format_func=lambda i: addr_labels[i],
            label_visibility="collapsed",
        )

    selected = addresses[selected_idx]  # type: ignore[index]
    selected_address = str(selected["address"])
    label = str(selected["label"] or "WHALE")

    with col_detail:
        st.subheader(f"{label}")
        st.caption(selected_address)

        last_active = int(selected["last_active_ms"] or 0)
        if last_active:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_active / 1000))
            st.caption(f"Last active: {ts}")

        tab_pos, tab_alerts = st.tabs(["Positions", "Alert History"])

        with tab_pos:
            positions = db_reader.get_whale_positions(selected_address)
            if not positions:
                st.info("No open positions found.")
            else:
                df = pl.DataFrame(
                    [
                        {
                            "Coin": p["coin"],
                            "Size": p["size"],
                            "Notional (USD)": p["notional_usd"],
                            "Unr. PnL": p["unrealized_pnl"],
                            "Liq. Price": p["liquidation_price"],
                            "Mark Price": p["mark_price"],
                        }
                        for p in positions
                    ]
                )
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Notional (USD)": st.column_config.NumberColumn(
                            format="$%,.0f"
                        ),
                        "Unr. PnL": st.column_config.NumberColumn(format="$%,.0f"),
                        "Mark Price": st.column_config.NumberColumn(format="$%,.4f"),
                        "Liq. Price": st.column_config.NumberColumn(format="$%,.4f"),
                    },
                )

        with tab_alerts:
            alert_rows = db_reader.get_alerts_by_address(selected_address)
            if not alert_rows:
                st.info("No alerts triggered by this address yet.")
            else:
                df_alerts = pl.DataFrame(
                    [
                        {
                            "Time": time.strftime(
                                "%Y-%m-%d %H:%M",
                                time.localtime(int(r["timestamp_ms"]) / 1000),
                            ),
                            "Type": r["alert_type"],
                            "Severity": r["severity"],
                            "Coin": r["coin"],
                            "Title": r["title"],
                        }
                        for r in alert_rows
                    ]
                )
                st.dataframe(df_alerts, width="stretch", hide_index=True)


def _render_top_traders(db_reader: DashboardReader) -> None:
    """Render top traders by volume for a selected coin."""
    st.subheader("Top Traders by Coin (last 1h)")

    coins = db_reader.get_distinct_coins()
    if not coins:
        st.info("No trade data available yet.")
        return

    selected_coin = st.selectbox("Coin", options=coins)
    if selected_coin is None:
        return

    rows = db_reader.get_top_whales(str(selected_coin), hours=1)
    if not rows:
        st.info(f"No trades for {selected_coin} in the last hour.")
        return

    df = pl.DataFrame(
        [
            {
                "Address": str(r["address"])[:16] + "...",
                "Volume (USD)": r["volume_usd"],
            }
            for r in rows[:10]
        ]
    )
    st.bar_chart(df, x="Address", y="Volume (USD)", width="stretch")
