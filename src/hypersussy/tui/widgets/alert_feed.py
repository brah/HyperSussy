"""Alert feed widget and detail modal."""

from __future__ import annotations

import datetime

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from hypersussy.models import Alert
from hypersussy.tui.messages import AlertReceived

_MAX_ALERTS = 500

_SEVERITY_MARKUP: dict[str, str] = {
    "critical": "bold red",
    "high": "bold yellow",
    "medium": "yellow",
    "low": "dim green",
}


def _severity_badge(severity: str) -> str:
    """Return a Rich markup badge for the given severity.

    Args:
        severity: One of low/medium/high/critical.

    Returns:
        Rich markup string for the severity badge.
    """
    style = _SEVERITY_MARKUP.get(severity, "white")
    return f"[{style}]{severity.upper()}[/{style}]"


def _format_alert_row(alert: Alert) -> str:
    """Format a single-line alert summary with Rich markup.

    Args:
        alert: The alert to summarise.

    Returns:
        Rich markup string for the list item label.
    """
    ts = datetime.datetime.fromtimestamp(
        alert.timestamp_ms / 1000, tz=datetime.UTC
    ).strftime("%H:%M:%S")
    badge = _severity_badge(alert.severity)
    return f"[dim]{ts}[/dim] {badge} [bold]{alert.coin}[/bold] — {alert.title}"


class AlertDetailScreen(ModalScreen[None]):
    """Full-screen modal showing alert description and metadata.

    Args:
        alert: The alert to display.
    """

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, alert: Alert) -> None:
        super().__init__()
        self._alert = alert

    def compose(self) -> ComposeResult:
        """Render alert detail content."""
        a = self._alert
        ts = datetime.datetime.fromtimestamp(
            a.timestamp_ms / 1000, tz=datetime.UTC
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        badge = _severity_badge(a.severity)

        lines = [
            f"{badge} [bold]{a.coin}[/bold] — {a.title}",
            f"[dim]{ts} | {a.alert_type} | {a.exchange}[/dim]",
            "",
            a.description,
        ]

        if a.metadata:
            lines.append("")
            lines.append("[bold underline]Metadata[/bold underline]")
            for key, value in a.metadata.items():
                if isinstance(value, list):
                    joined = ", ".join(str(v) for v in value)
                    lines.append(f"  [dim]{key}:[/dim] {joined}")
                elif isinstance(value, float):
                    lines.append(f"  [dim]{key}:[/dim] {value:.6g}")
                else:
                    lines.append(f"  [dim]{key}:[/dim] {value}")

        lines.append("")
        lines.append("[dim]Press Escape to close[/dim]")

        yield Static("\n".join(lines), id="alert-detail-content")


class AlertFeed(ListView):
    """Scrollable alert feed, newest first, capped at 500 items.

    Prepends a new ListItem for every AlertReceived message. Each item
    is colour-coded by severity. Pressing Enter opens a detail modal.
    """

    def on_alert_received(self, message: AlertReceived) -> None:
        """Prepend a new alert row to the list.

        Args:
            message: The incoming alert message.
        """
        alert = message.alert
        item = ListItem(
            Label(_format_alert_row(alert), markup=True),
        )
        # Store the Alert on the item for the detail modal
        item.alert = alert  # type: ignore[attr-defined]
        self.insert(0, [item])

        # Cap list length to bound memory
        while len(self._nodes) > _MAX_ALERTS:
            self._nodes[-1].remove()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open detail modal when an alert row is selected.

        Args:
            event: The selection event from Textual.
        """
        alert: Alert | None = getattr(event.item, "alert", None)
        if alert is not None:
            self.app.push_screen(AlertDetailScreen(alert))
