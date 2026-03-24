"""Status bar widget showing connection state and alert statistics."""

from __future__ import annotations

import datetime

from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Footer status bar displaying system health and alert statistics.

    Reactive attributes are updated by HyperSussyApp and automatically
    trigger a re-render via Textual's reactive system.
    """

    ws_connected: reactive[bool] = reactive(False)
    coin_count: reactive[int] = reactive(0)
    alert_count: reactive[int] = reactive(0)
    last_alert_ts: reactive[int] = reactive(0)  # epoch ms, 0 = never

    def render(self) -> str:
        """Render the status bar content.

        Returns:
            Rich markup string for the status bar.
        """
        ws_label = (
            "[bold green]WS: connected[/bold green]"
            if self.ws_connected
            else "[bold red]WS: disconnected[/bold red]"
        )
        coin_label = f"[dim]Coins:[/dim] {self.coin_count}"
        alert_label = f"[dim]Alerts today:[/dim] {self.alert_count}"

        if self.last_alert_ts > 0:
            ts = datetime.datetime.fromtimestamp(
                self.last_alert_ts / 1000, tz=datetime.UTC
            ).strftime("%H:%M:%S")
            last_label = f"[dim]Last alert:[/dim] {ts}"
        else:
            last_label = "[dim]Last alert:[/dim] —"

        parts = [ws_label, coin_label, alert_label, last_label]
        return "  |  ".join(parts)
