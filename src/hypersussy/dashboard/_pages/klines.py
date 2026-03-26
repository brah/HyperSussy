"""Kline (candlestick) chart page for the HyperSussy dashboard.

Renders a TradingView-quality candlestick + volume chart via
streamlit-lightweight-charts, followed by a top-holders concentration bar
and an hourly buy/sell trade-flow chart.
"""

from __future__ import annotations

import datetime

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from streamlit_lightweight_charts import (
    renderLightweightCharts,
)

from hypersussy.dashboard.components import (
    render_empty_state,
    render_page_header,
    render_section_header,
)
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.formatting import (
    CHART_FONT_COLOR,
    CHART_GRID,
    CHART_PAPER_BG,
    CHART_PLOT_BG,
    CHART_RED,
    CHART_TEAL,
)
from hypersussy.dashboard.navigation import short_wallet_label

# Candle interval options shown in the UI
_INTERVALS: list[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Lookback hours that correspond to each interval
_LOOKBACK_HOURS: dict[str, int] = {
    "1m": 4,
    "5m": 12,
    "15m": 24,
    "1h": 48,
    "4h": 168,
    "1d": 720,
}

# LWC chart theme applied to every chart instance
_LWC_CHART_OPTS: dict[str, object] = {
    "layout": {
        "background": {"type": "solid", "color": "#0e1117"},
        "textColor": "#fafafa",
    },
    "grid": {
        "vertLines": {"color": "#2a2d35"},
        "horzLines": {"color": "#2a2d35"},
    },
    "crosshair": {"mode": 1},
    "timeScale": {
        "timeVisible": True,
        "secondsVisible": False,
        "borderColor": "#2a2d35",
    },
    "rightPriceScale": {"borderColor": "#2a2d35"},
}


def render_klines(db_reader: DashboardReader, refresh_s: int) -> None:
    """Render the Klines page: candlestick, top-holders bar, trade flow.

    Args:
        db_reader: Read-only SQLite reader.
        refresh_s: Auto-refresh interval in seconds.
    """
    render_page_header(
        "Klines",
        "Candlestick charts with volume, top-holder concentration, and trade flow.",
    )

    coins = db_reader.get_distinct_coins()
    if not coins:
        render_empty_state(
            "No snapshot data available yet — candles populate as the monitor runs."
        )
        return

    col_coin, col_interval = st.columns([2, 3])
    with col_coin:
        coin = st.selectbox("Coin", options=coins, key="klines_coin")
    with col_interval:
        interval = st.pills(
            "Interval",
            options=_INTERVALS,
            default="1h",
            key="klines_interval",
        )

    if coin is None or interval is None:
        return

    coin_str = str(coin)
    interval_str = str(interval)

    @st.fragment(run_every=refresh_s)
    def _live() -> None:
        hours = _LOOKBACK_HOURS.get(interval_str, 48)
        _render_candlestick(db_reader, coin_str, interval_str, hours)
        st.divider()
        col_holders, col_flow = st.columns(2)
        with col_holders:
            _render_top_holders(db_reader, coin_str)
        with col_flow:
            _render_trade_flow(db_reader, coin_str)

    _live()


def _render_candlestick(
    db_reader: DashboardReader,
    coin: str,
    interval: str,
    hours: int,
) -> None:
    """Render the LWC candlestick + volume histogram.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
        interval: Candle interval string.
        hours: Lookback window in hours.
    """
    rows = db_reader.get_candles(coin, interval, hours=hours)
    if not rows:
        render_empty_state(
            f"No {interval} candles for {coin} yet. "
            "Candles are written as trades arrive — check back shortly."
        )
        return

    render_section_header(f"{coin} / {interval}", f"Last {hours}h of candle data.")

    df = pl.DataFrame(rows).sort("timestamp_ms")
    times_s: list[int] = (df["timestamp_ms"] // 1000).to_list()
    opens: list[float] = df["open"].cast(pl.Float64).to_list()
    highs: list[float] = df["high"].cast(pl.Float64).to_list()
    lows: list[float] = df["low"].cast(pl.Float64).to_list()
    closes: list[float] = df["close"].cast(pl.Float64).to_list()
    volumes: list[float] = df["volume"].cast(pl.Float64).to_list()

    candle_data: list[dict[str, object]] = [
        {"time": t, "open": o, "high": h, "low": lo, "close": c}
        for t, o, h, lo, c in zip(times_s, opens, highs, lows, closes, strict=False)
    ]
    volume_data: list[dict[str, object]] = [
        {
            "time": t,
            "value": v,
            "color": (
                "rgba(0,212,170,0.5)" if c >= o else "rgba(255,75,75,0.5)"
            ),
        }
        for t, v, c, o in zip(times_s, volumes, closes, opens, strict=False)
    ]

    series: list[dict[str, object]] = [
        {
            "type": "Candlestick",
            "data": candle_data,
            "options": {
                "upColor": CHART_TEAL,
                "downColor": CHART_RED,
                "borderUpColor": CHART_TEAL,
                "borderDownColor": CHART_RED,
                "wickUpColor": CHART_TEAL,
                "wickDownColor": CHART_RED,
            },
        },
        {
            "type": "Histogram",
            "data": volume_data,
            "options": {
                "color": "rgba(0,212,170,0.4)",
                "priceFormat": {"type": "volume"},
                "priceScaleId": "volume",
            },
            "priceScale": {
                "id": "volume",
                "scaleMargins": {"top": 0.82, "bottom": 0.0},
            },
        },
    ]

    renderLightweightCharts(
        [{"chart": _LWC_CHART_OPTS, "series": series}],
        key=f"lwc_{coin}_{interval}",
    )


def _render_top_holders(db_reader: DashboardReader, coin: str) -> None:
    """Render a horizontal bar chart of the top-15 holders by trade volume.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
    """
    rows = db_reader.get_top_holders_concentration(coin, hours=24, limit=15)
    if not rows:
        render_empty_state("No trade data for top holders yet.")
        return

    render_section_header("Top Holders", f"By 24h trade volume — {coin}.")

    df = pl.DataFrame(rows)
    total: float = df["total_volume"].cast(pl.Float64)[0]
    raw_addresses: list[str] = df["address"].cast(pl.Utf8).to_list()
    volumes: list[float] = df["volume_usd"].cast(pl.Float64).to_list()

    addresses = [short_wallet_label(a) for a in raw_addresses]
    pcts = [v / total * 100 for v in volumes]
    bar_colors = [
        f"rgba(0,212,170,{max(0.35, min(0.95, v / total + 0.3)):.2f})"
        for v in volumes
    ]

    fig = go.Figure(
        go.Bar(
            x=volumes,
            y=addresses,
            orientation="h",
            marker_color=bar_colors,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Volume: $%{x:,.0f}<br>"
                "Share: %{customdata[1]:.1f}%<extra></extra>"
            ),
            customdata=[[a, p] for a, p in zip(addresses, pcts, strict=False)],
        )
    )
    fig.update_layout(
        height=320,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        plot_bgcolor=CHART_PLOT_BG,
        paper_bgcolor=CHART_PAPER_BG,
        font={"color": CHART_FONT_COLOR},
        xaxis={
            "tickprefix": "$",
            "tickformat": ",.0f",
            "gridcolor": CHART_GRID,
            "showgrid": True,
        },
        yaxis={"gridcolor": CHART_GRID, "autorange": "reversed"},
    )
    st.plotly_chart(fig, width="stretch")


def _render_trade_flow(db_reader: DashboardReader, coin: str) -> None:
    """Render an hourly buy/sell trade-flow bar chart.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
    """
    rows = db_reader.get_trade_flow_by_hour(coin, hours=24)
    if not rows:
        render_empty_state("No trade flow data yet.")
        return

    render_section_header("Trade Flow", f"Hourly buy vs sell — {coin}.")

    df = pl.DataFrame(rows).with_columns(
        pl.col("bucket").cast(pl.Int64),
        pl.col("volume_usd").cast(pl.Float64),
    )
    buy_df = df.filter(pl.col("side") == "B").select(["bucket", "volume_usd"])
    sell_df = df.filter(pl.col("side") == "A").select(["bucket", "volume_usd"])

    all_buckets: list[int] = sorted(
        set(buy_df["bucket"].to_list()) | set(sell_df["bucket"].to_list())
    )
    buy_map: dict[int, float] = dict(
        zip(buy_df["bucket"].to_list(), buy_df["volume_usd"].to_list(), strict=False)
    )
    sell_map: dict[int, float] = dict(
        zip(
            sell_df["bucket"].to_list(),
            sell_df["volume_usd"].to_list(),
            strict=False,
        )
    )

    times = [
        datetime.datetime.fromtimestamp(b / 1000, tz=datetime.UTC)
        for b in all_buckets
    ]
    buy_vols = [buy_map.get(b, 0.0) for b in all_buckets]
    sell_vols = [sell_map.get(b, 0.0) for b in all_buckets]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=times,
            y=buy_vols,
            name="Buy",
            marker_color="rgba(0,212,170,0.7)",
            hovertemplate="Buy: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=times,
            y=[-v for v in sell_vols],
            name="Sell",
            marker_color="rgba(255,75,75,0.7)",
            hovertemplate="Sell: $%{customdata:,.0f}<extra></extra>",
            customdata=sell_vols,
        )
    )
    fig.update_layout(
        barmode="relative",
        height=320,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        plot_bgcolor=CHART_PLOT_BG,
        paper_bgcolor=CHART_PAPER_BG,
        font={"color": CHART_FONT_COLOR},
        xaxis={"gridcolor": CHART_GRID},
        yaxis={
            "tickprefix": "$",
            "tickformat": ",.0f",
            "gridcolor": CHART_GRID,
            "zeroline": True,
            "zerolinecolor": "#555555",
            "zerolinewidth": 1,
        },
        legend={"orientation": "h", "y": 1.05},
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")
