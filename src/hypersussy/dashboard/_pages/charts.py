"""Historical charts page for the HyperSussy dashboard."""

from __future__ import annotations

import polars as pl
import streamlit as st

from hypersussy.dashboard.db_reader import DashboardReader


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


def _render_oi_chart(
    db_reader: DashboardReader,
    coin: str,
    hours: int,
) -> None:
    """Render open interest history line chart.

    Args:
        db_reader: Read-only SQLite reader.
        coin: Asset ticker symbol.
        hours: Lookback window in hours.
    """
    rows = db_reader.get_oi_history(coin, hours=hours)
    if not rows:
        st.warning(f"No OI history for {coin} in the last {hours}h.")
        return

    df = pl.DataFrame(rows).with_columns(
        (pl.col("timestamp_ms") / 1000).cast(pl.Datetime("ms")).alias("time")
    )

    st.subheader(f"Open Interest — {coin}")
    st.line_chart(
        df.select(["time", "open_interest_usd"]).to_pandas().set_index("time"),
        width="stretch",
    )


def _render_funding_price_charts(
    db_reader: DashboardReader,
    coin: str,
    hours: int,
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

    df = pl.DataFrame(rows).with_columns(
        (pl.col("timestamp_ms") / 1000).cast(pl.Datetime("ms")).alias("time")
    )

    col_funding, col_price = st.columns(2)

    with col_funding:
        st.subheader("Funding Rate")
        st.line_chart(
            df.select(["time", "funding_rate"]).to_pandas().set_index("time"),
            width="stretch",
        )

    with col_price:
        st.subheader("Mark vs Oracle Price")
        price_df = (
            df.select(["time", "mark_price", "oracle_price"])
            .to_pandas()
            .set_index("time")
        )
        st.line_chart(price_df, width="stretch")
