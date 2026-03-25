"""Historical charts page for the HyperSussy dashboard."""

from __future__ import annotations

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import (
    CHART_FONT_COLOR,
    CHART_GRID,
    CHART_ORANGE,
    CHART_PAPER_BG,
    CHART_PLOT_BG,
    CHART_RED,
    CHART_TEAL,
    price_d3_format,
)


def _base_layout(**kwargs: object) -> dict[str, object]:
    """Return a base Plotly layout dict with consistent dark styling.

    Args:
        **kwargs: Additional layout overrides.

    Returns:
        Layout dict suitable for go.Figure(layout=...).
    """
    layout: dict[str, object] = {
        "plot_bgcolor": CHART_PLOT_BG,
        "paper_bgcolor": CHART_PAPER_BG,
        "font": {"color": CHART_FONT_COLOR},
        "margin": {"l": 10, "r": 10, "t": 30, "b": 10},
        "xaxis": {"gridcolor": CHART_GRID, "showgrid": True},
        "yaxis": {"gridcolor": CHART_GRID, "showgrid": True},
        "hovermode": "x unified",
    }
    layout.update(kwargs)
    return layout


def render_charts(db_reader: DashboardReader) -> None:
    """Render historical OI, funding rate, and price charts for a coin.

    Args:
        db_reader: Read-only SQLite reader.
    """
    st.header("Historical Charts")

    coins = db_reader.get_distinct_coins()
    if not coins:
        st.info("No snapshot data available yet.")
        return

    col_coin, col_tf = st.columns(2)
    with col_coin:
        coin = st.selectbox("Coin", options=coins)
    with col_tf:
        hours = st.select_slider(
            "Timeframe",
            options=[1, 6, 12, 24, 48, 168],
            value=24,
            format_func=lambda h: f"{h}h",
        )

    if coin is None:
        return

    coin_str = str(coin)
    hours_int = int(hours)  # type: ignore[arg-type]

    _render_oi_chart(db_reader, coin_str, hours_int)
    _render_funding_price_charts(db_reader, coin_str, hours_int)


def _render_oi_chart(db_reader: DashboardReader, coin: str, hours: int) -> None:
    """Render open interest history as a filled Plotly line chart.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
        hours: Lookback window in hours.
    """
    rows = db_reader.get_oi_history(coin, hours=hours)
    if not rows:
        st.warning(f"No OI history for {coin} in the last {hours}h.")
        return

    df = (
        pl.DataFrame(rows)
        .with_columns(
            (pl.col("timestamp_ms") / 1000).cast(pl.Datetime("ms")).alias("time")
        )
        .sort("time")
    )

    times = df["time"].to_list()
    oi_vals = df["open_interest_usd"].to_list()

    fig = go.Figure(
        go.Scatter(
            x=times,
            y=oi_vals,
            mode="lines",
            fill="tozeroy",
            line={"color": CHART_TEAL, "width": 2},
            fillcolor="rgba(0,212,170,0.15)",
            name="OI (USD)",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title=f"Open Interest — {coin}",
            yaxis={"tickprefix": "$", "tickformat": ",.0f", "gridcolor": CHART_GRID},
            xaxis={"rangeslider": {"visible": True}, "gridcolor": CHART_GRID},
        )
    )
    st.plotly_chart(fig, width="stretch")


def _render_funding_price_charts(
    db_reader: DashboardReader, coin: str, hours: int
) -> None:
    """Render funding rate and mark/oracle price charts side-by-side.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
        hours: Lookback window in hours.
    """
    rows = db_reader.get_funding_history(coin, hours=hours)
    if not rows:
        return

    df = (
        pl.DataFrame(rows)
        .with_columns(
            (pl.col("timestamp_ms") / 1000).cast(pl.Datetime("ms")).alias("time")
        )
        .sort("time")
    )

    times = df["time"].to_list()
    funding = df["funding_rate"].to_list()
    mark = df["mark_price"].to_list()
    oracle = df["oracle_price"].to_list()

    col_funding, col_price = st.columns(2)

    with col_funding:
        pos_y = [max(v, 0.0) for v in funding]
        neg_y = [min(v, 0.0) for v in funding]
        fig_f = go.Figure()
        fig_f.add_trace(
            go.Scatter(
                x=times,
                y=pos_y,
                mode="lines",
                fill="tozeroy",
                line={"color": CHART_TEAL, "width": 1},
                fillcolor="rgba(0,212,170,0.2)",
                name="Positive",
                hovertemplate="%{y:.5f}%<extra></extra>",
            )
        )
        fig_f.add_trace(
            go.Scatter(
                x=times,
                y=neg_y,
                mode="lines",
                fill="tozeroy",
                line={"color": CHART_RED, "width": 1},
                fillcolor="rgba(255,75,75,0.2)",
                name="Negative",
                hovertemplate="%{y:.5f}%<extra></extra>",
            )
        )
        fig_f.add_hline(y=0, line_dash="dot", line_color="#666666", line_width=1)
        fig_f.update_layout(**_base_layout(title="Funding Rate", showlegend=False))
        st.plotly_chart(fig_f, width="stretch")

    with col_price:
        # Determine format from representative price
        rep_price = next((v for v in mark if v > 0), 0.0)
        d3_fmt = price_d3_format(rep_price)

        fig_p = go.Figure()
        fig_p.add_trace(
            go.Scatter(
                x=times,
                y=mark,
                mode="lines",
                line={"color": CHART_TEAL, "width": 2},
                name="Mark",
                hovertemplate=f"Mark: $%{{y:{d3_fmt}}}<extra></extra>",
            )
        )
        fig_p.add_trace(
            go.Scatter(
                x=times,
                y=oracle,
                mode="lines",
                line={"color": CHART_ORANGE, "width": 2, "dash": "dot"},
                name="Oracle",
                hovertemplate=f"Oracle: $%{{y:{d3_fmt}}}<extra></extra>",
            )
        )
        fig_p.update_layout(
            **_base_layout(
                title="Mark vs Oracle Price",
                yaxis={
                    "tickprefix": "$",
                    "tickformat": d3_fmt,
                    "gridcolor": CHART_GRID,
                },
                legend={"orientation": "h", "y": 1.1},
            )
        )
        st.plotly_chart(fig_p, width="stretch")
