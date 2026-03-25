"""Wallet detail page for the HyperSussy dashboard."""

from __future__ import annotations

import time

import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import (
    build_positions_df,
    format_price,
    severity_color,
)


def render_wallet_detail(db_reader: DashboardReader, refresh_s: int) -> None:
    """Render a deep-dive view for a single wallet address.

    Accessed via query params ``?page=wallet&address=0x...``.
    Shows positions, trade history, and alerts for the address.

    Args:
        db_reader: Read-only SQLite reader.
        refresh_s: Auto-refresh interval in seconds.
    """
    address = st.query_params.get("address", "")

    if not address or not address.startswith("0x") or len(address) != 42:
        st.warning("Invalid or missing wallet address.")
        if st.button("Back to dashboard"):
            st.query_params.clear()
            st.rerun()
        return

    if st.button("Back"):
        st.query_params.clear()
        st.rerun()

    st.header(f"Wallet ...{address[-10:]}")
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
        st.info("No open positions found.")
        return

    df = build_positions_df(positions, db_reader.get_latest_oi_per_coin())
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "Notional (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "Unr. PnL": st.column_config.NumberColumn(format="$%+,.0f"),
        },
    )


def _render_trades(db_reader: DashboardReader, address: str) -> None:
    """Render recent trade history for the wallet."""
    hours = st.select_slider(
        "Lookback",
        options=[1, 4, 24, 48, 168],
        value=24,
        format_func=lambda h: f"{h}h",
        key="wallet_trade_hours",
    )

    rows = db_reader.get_trades_by_address(address, hours=int(hours))  # type: ignore[arg-type]
    if not rows:
        st.info(f"No trades in the last {hours}h.")
        return

    df = pl.DataFrame(
        [
            {
                "Time": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(int(r["timestamp_ms"]) / 1000),
                ),
                "Coin": r["coin"],
                "Side": "BUY" if r["side"] == "B" else "SELL",
                "Size": float(r["size"]),
                "Price": format_price(float(r["price"])),
                "Notional": float(r["price"]) * float(r["size"]),
            }
            for r in rows
        ]
    )
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "Notional": st.column_config.NumberColumn(format="$%,.0f"),
        },
    )


def _render_alerts(db_reader: DashboardReader, address: str) -> None:
    """Render colour-coded alert history for the wallet."""
    alert_rows = db_reader.get_alerts_by_address(address, limit=50)
    if not alert_rows:
        st.info("No alerts triggered by this address yet.")
        return

    for r in alert_rows:
        severity = str(r["severity"])
        color = severity_color(severity)
        ts = time.strftime(
            "%H:%M:%S", time.localtime(int(r["timestamp_ms"]) / 1000)
        )
        st.markdown(
            f'<span style="color:{color};font-weight:bold">'
            f"[{severity.upper()}]</span> "
            f'`{r["coin"]}` | {r["alert_type"]} | '
            f'**{r["title"]}** | _{ts}_',
            unsafe_allow_html=True,
        )
