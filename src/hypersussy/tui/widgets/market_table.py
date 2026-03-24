"""Live market data table widget."""

from __future__ import annotations

from textual.widgets import DataTable

from hypersussy.tui.messages import SnapshotUpdated

_COLUMNS = [
    ("coin", "Coin"),
    ("mark_price", "Mark Price"),
    ("open_interest_usd", "OI (USD)"),
    ("funding_rate", "Funding Rate"),
    ("day_volume_usd", "24h Volume"),
    ("premium", "Premium"),
]


def _fmt_price(value: float) -> str:
    """Format a price with up to 4 significant figures.

    Args:
        value: Raw price float.

    Returns:
        Formatted price string.
    """
    if value >= 1_000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def _fmt_usd(value: float) -> str:
    """Format a USD value with M/B suffix.

    Args:
        value: Raw USD float.

    Returns:
        Human-readable USD string.
    """
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def _fmt_rate(value: float) -> str:
    """Format a funding/premium rate as a percentage.

    Args:
        value: Raw rate float (e.g. 0.0001).

    Returns:
        Percentage string with sign.
    """
    pct = value * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.4f}%"


class MarketTable(DataTable):  # type: ignore[type-arg]
    """Live per-coin market data table.

    Displays mark price, OI, funding rate, 24h volume, and premium for
    each tracked coin. Rows are added on first sight and updated in-place
    on subsequent snapshots using stable row keys for O(1) updates.
    """

    def on_mount(self) -> None:
        """Add columns when the widget is mounted."""
        self._seen_coins: set[str] = set()
        for key, label in _COLUMNS:
            self.add_column(label, key=key)
        self.cursor_type = "row"
        self.zebra_stripes = True

    def on_snapshot_updated(self, message: SnapshotUpdated) -> None:
        """Update or insert a row when a snapshot arrives.

        Args:
            message: The incoming snapshot message.
        """
        snap = message.snapshot
        row_values = [
            snap.coin,
            _fmt_price(snap.mark_price),
            _fmt_usd(snap.open_interest_usd),
            _fmt_rate(snap.funding_rate),
            _fmt_usd(snap.day_volume_usd),
            _fmt_rate(snap.premium),
        ]

        if snap.coin in self._seen_coins:
            for (col_key, _), value in zip(_COLUMNS, row_values, strict=True):
                self.update_cell(snap.coin, col_key, value, update_width=False)
        else:
            self._seen_coins.add(snap.coin)
            self.add_row(*row_values, key=snap.coin)
