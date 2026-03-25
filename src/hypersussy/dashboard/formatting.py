"""Shared formatting helpers for the HyperSussy dashboard."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence

import polars as pl

# -- Chart colour palette (shared across charts.py and whale_tracker.py) --

CHART_TEAL = "#00d4aa"
CHART_RED = "#ff4b4b"
CHART_ORANGE = "#ffa500"
CHART_GRID = "#2a2d35"
CHART_GREY = "#4a4e69"
CHART_PAPER_BG = "rgba(0,0,0,0)"
CHART_PLOT_BG = "rgba(0,0,0,0)"
CHART_FONT_COLOR = "#fafafa"

# -- Severity helpers --

_SEV_COLORS: dict[str, str] = {
    "critical": "#ff4b4b",
    "high": "#ffa500",
    "medium": "#ffd700",
    "low": "#21c354",
}

SEV_RANK: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def format_price(value: float) -> str:
    """Format a price with smart decimal precision.

    Prices >= $1 get 2 decimal places.  Prices < $1 show all leading
    zeros plus 2 significant digits so micro-prices remain readable.

    Args:
        value: Dollar amount (may be negative).

    Returns:
        Formatted string with ``$`` prefix, e.g. ``$1,710.53`` or
        ``$0.0000001953``.
    """
    if value == 0:
        return "$0.00"
    negative = value < 0
    v = abs(value)
    if v >= 1.0:
        result = f"${v:,.2f}"
    else:
        leading_zeros = max(0, math.floor(-math.log10(v)))
        decimals = leading_zeros + 2
        result = f"${v:.{decimals}f}"
    return f"-{result}" if negative else result


def price_d3_format(representative: float) -> str:
    """Return a d3-format string appropriate for *representative*.

    Suitable for Plotly ``tickformat`` and ``hovertemplate`` fields.

    Args:
        representative: A typical price from the data series.

    Returns:
        d3-format string, e.g. ``",.2f"`` or ``",.10f"``.
    """
    if representative <= 0 or representative >= 1.0:
        return ",.2f"
    leading_zeros = max(0, math.floor(-math.log10(representative)))
    return f",.{leading_zeros + 2}f"


def severity_color(severity: str) -> str:
    """Map an alert severity to a hex colour.

    Args:
        severity: One of ``critical``, ``high``, ``medium``, ``low``.

    Returns:
        Hex colour string.
    """
    return _SEV_COLORS.get(severity, "#cccccc")


def render_alert_line(
    severity: str,
    coin: str,
    title: str,
    timestamp_ms: int,
    alert_type: str = "",
    address: str | None = None,
) -> str:
    """Return an HTML string for a single colour-coded alert line.

    Args:
        severity: Alert severity level.
        coin: Asset ticker symbol.
        title: Alert title text.
        timestamp_ms: Alert timestamp in milliseconds.
        alert_type: Optional engine alert type string.
        address: Optional wallet address for a clickable link.

    Returns:
        HTML string for use with ``st.markdown(unsafe_allow_html=True)``.
    """
    color = severity_color(severity)
    ts = time.strftime("%H:%M:%S", time.localtime(timestamp_ms / 1000))
    type_part = f" | {alert_type}" if alert_type else ""
    addr_part = f" | {wallet_link_html(address)}" if address else ""
    return (
        f'<span style="color:{color};font-weight:bold">'
        f"[{severity.upper()}]</span> "
        f"`{coin}`{type_part} | "
        f"**{title}** | _{ts}_{addr_part}"
    )


def sort_alerts_by_severity(
    rows: Sequence[dict[str, object]],
    ts_key: str = "timestamp_ms",
) -> list[dict[str, object]]:
    """Sort alert dicts by severity (critical first), then newest first.

    Args:
        rows: Alert dicts with ``severity`` and a timestamp key.
        ts_key: Name of the timestamp key in each dict.

    Returns:
        Sorted copy of the input list.
    """
    return sorted(
        rows,
        key=lambda r: (
            SEV_RANK.get(str(r["severity"]), 9),
            -int(r[ts_key]),  # type: ignore[call-overload]
        ),
    )


def wallet_link_html(address: str) -> str:
    """Return an HTML anchor that navigates to the wallet detail page.

    Args:
        address: Full 0x address.

    Returns:
        HTML ``<a>`` tag for use with ``unsafe_allow_html=True``.
    """
    short = f"...{address[-8:]}"
    return (
        f'<a href="?page=wallet&address={address}" '
        f'target="_self" style="color:#00d4aa">{short}</a>'
    )


def build_positions_df(
    positions: list[dict[str, object]],
    oi_by_coin: dict[str, float],
) -> pl.DataFrame:
    """Build a display DataFrame for positions with OI% and liq distance.

    Args:
        positions: Position dicts from ``DashboardReader.get_whale_positions``.
        oi_by_coin: Latest open interest per coin in base units.

    Returns:
        Polars DataFrame with columns: Coin, Size (%OI), Notional (USD),
        Unr. PnL, Mark Price, Liq. Price, Liq. Distance.
    """
    rows = []
    for p in positions:
        coin = str(p["coin"])
        size = float(p["size"] or 0)
        mark = float(p["mark_price"] or 0)
        liq = float(p["liquidation_price"] or 0)
        oi = oi_by_coin.get(coin, 0.0)

        abs_size = abs(size)
        if oi > 0:
            oi_pct = abs_size / oi * 100
            size_str = f"{abs_size:,.0f} ({oi_pct:.1f}%)"
        else:
            size_str = f"{abs_size:,.0f}"

        if mark > 0 and liq > 0:
            liq_dist_pct = (liq - mark) / mark * 100
            liq_dist_str = f"{liq_dist_pct:+.1f}%"
        else:
            liq_dist_str = "N/A"

        rows.append(
            {
                "Coin": coin,
                "Size (%OI)": size_str,
                "Notional (USD)": float(p["notional_usd"] or 0),
                "Unr. PnL": float(p["unrealized_pnl"] or 0),
                "Mark Price": format_price(mark),
                "Liq. Price": format_price(liq),
                "Liq. Distance": liq_dist_str,
            }
        )
    return (
        pl.DataFrame(rows)
        if rows
        else pl.DataFrame(
            schema={
                "Coin": pl.Utf8,
                "Size (%OI)": pl.Utf8,
                "Notional (USD)": pl.Float64,
                "Unr. PnL": pl.Float64,
                "Mark Price": pl.Utf8,
                "Liq. Price": pl.Utf8,
                "Liq. Distance": pl.Utf8,
            }
        )
    )
