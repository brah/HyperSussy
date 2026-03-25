"""Whale tracker page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import plotly.graph_objects as go
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import (
    build_positions_df,
    severity_color,
    wallet_link_html,
)

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
    # Manual whale add form
    with st.expander("Add whale manually"):  # noqa: SIM117
        with st.form("add_whale_form", clear_on_submit=True):
            new_addr = st.text_input("Address (0x...)")
            new_label = st.text_input("Label (optional)", value="")
            submitted = st.form_submit_button("Add")
            if submitted:
                addr = new_addr.strip()
                if addr.startswith("0x") and len(addr) == 42:
                    db_reader.insert_tracked_address(
                        addr, new_label.strip() or "MANUAL"
                    )
                    st.rerun()
                else:
                    st.error("Address must be a 42-character 0x hex string.")

    addresses = db_reader.get_tracked_addresses(limit=100)

    if not addresses:
        st.info(
            "No tracked whale addresses yet. "
            "Threshold: $5M volume or 5% of coin OI in 1h."
        )
        return

    col_list, col_detail = st.columns([1, 2])

    with col_list:
        st.subheader("Tracked Whales")
        addr_labels = [
            f"{row['label'] or 'WHALE'} -- ${row['total_volume_usd']:>,.0f}"
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

        col_actions = st.columns([1, 1, 2])
        with col_actions[0]:
            if st.button("View wallet", key=f"view_{selected_address}"):
                st.query_params["page"] = "wallet"
                st.query_params["address"] = selected_address
                st.rerun()
        with col_actions[1]:
            if st.button("Remove", key=f"del_{selected_address}"):
                db_reader.delete_tracked_address(selected_address)
                st.rerun()

        last_active = int(selected["last_active_ms"] or 0)
        if last_active:
            ts = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(last_active / 1000)
            )
            st.caption(f"Last active: {ts}")

        tab_pos, tab_alerts = st.tabs(["Positions", "Alert History"])

        with tab_pos:
            positions = db_reader.get_whale_positions(selected_address)
            if not positions:
                st.info("No open positions found.")
            else:
                df = build_positions_df(
                    positions, db_reader.get_latest_oi_per_coin()
                )
                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Notional (USD)": st.column_config.NumberColumn(
                            format="$%,.0f"
                        ),
                        "Unr. PnL": st.column_config.NumberColumn(
                            format="$%+,.0f"
                        ),
                    },
                )

        with tab_alerts:
            alert_rows = db_reader.get_alerts_by_address(selected_address)
            if not alert_rows:
                st.info("No alerts triggered by this address yet.")
            else:
                sev_rank = {
                    "critical": 0,
                    "high": 1,
                    "medium": 2,
                    "low": 3,
                }
                sorted_rows = sorted(
                    alert_rows,
                    key=lambda r: sev_rank.get(str(r["severity"]), 9),
                )
                for r in sorted_rows:
                    severity = str(r["severity"])
                    color = severity_color(severity)
                    ts = time.strftime(
                        "%H:%M:%S",
                        time.localtime(int(r["timestamp_ms"]) / 1000),
                    )
                    st.markdown(
                        f'<span style="color:{color};font-weight:bold">'
                        f"[{severity.upper()}]</span> "
                        f'`{r["coin"]}` | {r["alert_type"]} | '
                        f'**{r["title"]}** | _{ts}_',
                        unsafe_allow_html=True,
                    )


def _render_top_traders(db_reader: DashboardReader) -> None:
    """Render top traders by volume for a selected coin."""
    st.subheader("Top Traders by Coin")

    coins = db_reader.get_distinct_coins()
    if not coins:
        st.info("No trade data available yet.")
        return

    col_coin, col_hours = st.columns(2)
    with col_coin:
        selected_coin = st.selectbox(
            "Coin", options=coins, key="top_traders_coin"
        )
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

    # Horizontal Plotly bar chart -- sorted ascending so largest is at top
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
        xaxis={
            "tickprefix": "$",
            "tickformat": ",.0f",
            "gridcolor": "#2a2d35",
        },
        yaxis={"gridcolor": "#2a2d35"},
    )
    st.plotly_chart(fig, width="stretch")

    # Ranked summary table with wallet hotlinks
    table_html_parts = [
        "<table style='width:100%;border-collapse:collapse;"
        "font-size:0.9em;color:#fafafa'>"
        + "<tr style='border-bottom:1px solid #2a2d35'>"
        + "<th>Rank</th><th>Address</th>"
        + "<th>Volume (USD)</th><th>% of Top 10</th>"
        + "<th>Tracked</th></tr>"
    ]
    for i, r in enumerate(top10):
        addr = str(r["address"])
        vol = float(r["volume_usd"])
        pct = vol / total_vol * 100
        tracked = addr in tracked_set
        link = wallet_link_html(addr)
        tracked_mark = "Y" if tracked else ""
        table_html_parts.append(
            f"<tr style='border-bottom:1px solid #1a1d24'>"
            f"<td>{i + 1}</td>"
            f"<td>{link}</td>"
            f"<td>${vol:,.0f}</td>"
            f"<td>{pct:.1f}%</td>"
            f"<td>{tracked_mark}</td></tr>"
        )
    table_html_parts.append("</table>")
    st.markdown("".join(table_html_parts), unsafe_allow_html=True)
