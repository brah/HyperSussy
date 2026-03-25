"""Whale tracker page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader

_TEAL = "#00d4aa"
_GREY = "#4a4e69"
_HOURS_OPTIONS = [1, 4, 24]
_COL_VOLUME = "Volume (USD)"


def render_whale_tracker(db_reader: DashboardReader, refresh_s: int) -> None:
    """Render the whale tracking page.

    Displays tracked whale addresses with drill-down into positions and
    alert history, and top traders by coin with a Plotly horizontal bar
    chart and ranked summary table.

    Args:
        db_reader: Read-only SQLite reader.
        refresh_s: Auto-refresh interval in seconds.
    """
    st.header("Whale Tracker")

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        _render_address_panel(db_reader)
        st.divider()
        _render_top_traders(db_reader)

    _live()


def _render_address_panel(db_reader: DashboardReader) -> None:
    """Two-column layout: address list and selected address detail."""
    addresses = db_reader.get_tracked_addresses(limit=100)

    if not addresses:
        st.info("No tracked whale addresses yet. Threshold: $5M volume or 5% of coin OI in 1h.")
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
        st.subheader(label)
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
                        "Unr. PnL": st.column_config.NumberColumn(format="$%+,.0f"),
                        "Mark Price": st.column_config.NumberColumn(format="$%,.4f"),
                        "Liq. Price": st.column_config.NumberColumn(format="$%,.4f"),
                    },
                )

        with tab_alerts:
            alert_rows = db_reader.get_alerts_by_address(selected_address)
            if not alert_rows:
                st.info("No alerts triggered by this address yet.")
            else:
                _SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                _SEV_BADGE = {
                    "critical": "[CRIT]",
                    "high": "[HIGH]",
                    "medium": "[ MED]",
                    "low": "[ LOW]",
                }
                sorted_rows = sorted(
                    alert_rows,
                    key=lambda r: _SEV_RANK.get(str(r["severity"]), 9),
                )
                df_alerts = pl.DataFrame(
                    [
                        {
                            "Level": _SEV_BADGE.get(str(r["severity"]), str(r["severity"])),
                            "Time": time.strftime(
                                "%Y-%m-%d %H:%M",
                                time.localtime(int(r["timestamp_ms"]) / 1000),
                            ),
                            "Type": r["alert_type"],
                            "Coin": r["coin"],
                            "Title": r["title"],
                        }
                        for r in sorted_rows
                    ]
                )
                st.dataframe(df_alerts, width="stretch", hide_index=True)


def _render_top_traders(db_reader: DashboardReader) -> None:
    """Render top traders by volume for a selected coin."""
    st.subheader("Top Traders by Coin")

    coins = db_reader.get_distinct_coins()
    if not coins:
        st.info("No trade data available yet.")
        return

    col_coin, col_hours = st.columns(2)
    with col_coin:
        selected_coin = st.selectbox("Coin", options=coins, key="top_traders_coin")
    with col_hours:
        hours = st.selectbox(
            "Lookback",
            options=_HOURS_OPTIONS,
            format_func=lambda h: f"{h}h",
            key="top_traders_hours",
        )

    if selected_coin is None:
        return

    rows = db_reader.get_top_whales(str(selected_coin), hours=int(hours))  # type: ignore[arg-type]
    if not rows:
        st.info(f"No trades for {selected_coin} in the last {hours}h.")
        return

    tracked_set = {
        str(r["address"]) for r in db_reader.get_tracked_addresses(limit=1000)
    }

    top10 = rows[:10]
    total_vol = sum(float(r["volume_usd"]) for r in top10) or 1.0

    # Horizontal Plotly bar chart — sorted ascending so largest is at top
    sorted_rows = sorted(top10, key=lambda r: float(r["volume_usd"]))
    addresses = [str(r["address"]) for r in sorted_rows]
    volumes = [float(r["volume_usd"]) for r in sorted_rows]
    colours = [_TEAL if a in tracked_set else _GREY for a in addresses]
    short_labels = [f"...{a[-10:]}" for a in addresses]
    hover = [
        f"<b>{a}</b><br>Volume: ${v:,.0f}"
        for a, v in zip(addresses, volumes, strict=False)
    ]

    fig = go.Figure(
        go.Bar(
            x=volumes,
            y=short_labels,
            orientation="h",
            marker_color=colours,
            hovertext=hover,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        xaxis_title=_COL_VOLUME,
        yaxis_title=None,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        height=320,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#fafafa",
        xaxis={"tickprefix": "$", "tickformat": ",.0f", "gridcolor": "#2a2d35"},
        yaxis={"gridcolor": "#2a2d35"},
    )
    st.plotly_chart(fig, use_container_width=True)

    # Ranked summary table
    df = pl.DataFrame(
        [
            {
                "Rank": i + 1,
                "Address": str(r["address"]),
                _COL_VOLUME: float(r["volume_usd"]),
                "% of Top 10": float(r["volume_usd"]) / total_vol * 100,
                "Tracked": str(r["address"]) in tracked_set,
            }
            for i, r in enumerate(top10)
        ]
    )
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            _COL_VOLUME: st.column_config.ProgressColumn(
                format="$%,.0f",
                min_value=0,
                max_value=total_vol,
            ),
            "% of Top 10": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
