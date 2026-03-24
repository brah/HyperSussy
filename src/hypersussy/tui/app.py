"""Main Textual application for HyperSussy TUI.

The app implements DataBus so the orchestrator and TuiSink can push
data in without importing Textual types directly. The orchestrator runs
as a Textual Worker inside the same event loop, so post_message() calls
are always same-loop and require no thread bridging.

Message routing: push_snapshot and push_alert post messages directly to
the child widgets that handle them (MarketTable and AlertFeed) rather
than posting to the App and relying on bubbling. The App-level handlers
(on_alert_received) handle cross-cutting concerns like StatusBar updates.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Label

from hypersussy.models import Alert, AssetSnapshot
from hypersussy.tui.messages import AlertReceived, SnapshotUpdated
from hypersussy.tui.widgets.alert_feed import AlertFeed
from hypersussy.tui.widgets.market_table import MarketTable
from hypersussy.tui.widgets.status_bar import StatusBar

if TYPE_CHECKING:
    from hypersussy.orchestrator import Orchestrator

_CSS_PATH = Path(__file__).parent / "css" / "app.tcss"


class HyperSussyApp(App[None]):
    """HyperSussy monitoring TUI.

    Implements the DataBus protocol so the orchestrator and TuiSink can
    push live data without importing App directly.
    """

    CSS_PATH = _CSS_PATH
    TITLE = "HyperSussy"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("Q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._orchestrator: Orchestrator | None = None
        self._alert_count: int = 0
        self._seen_coins: set[str] = set()

    def set_orchestrator(self, orchestrator: Orchestrator) -> None:
        """Inject the orchestrator before the app is run.

        Must be called before run_async(). Allows the CLI to construct
        the app first (to obtain the DataBus reference), then wire up
        the orchestrator with app as its data_bus.

        Args:
            orchestrator: The fully initialised orchestrator.
        """
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # DataBus implementation
    # ------------------------------------------------------------------

    def push_snapshot(self, snapshot: AssetSnapshot) -> None:
        """Forward a snapshot directly to the MarketTable widget.

        Args:
            snapshot: The asset snapshot to display.
        """
        self._seen_coins.add(snapshot.coin)
        self.query_one(MarketTable).post_message(SnapshotUpdated(snapshot))

    def push_alert(self, alert: Alert) -> None:
        """Forward an alert to the AlertFeed widget and update the App.

        Args:
            alert: The alert to display.
        """
        self._alert_count += 1
        # Post to the app for cross-cutting handlers (StatusBar update),
        # then also directly to AlertFeed so it renders the item.
        self.post_message(AlertReceived(alert))
        self.query_one(AlertFeed).post_message(AlertReceived(alert))

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        now = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
        yield Label(f"HyperSussy  |  {now}", id="header")
        with Vertical(id="main-split"):
            yield Label("Market Data", id="market-table-label")
            yield MarketTable(id="market-table")
            yield Label("Alerts", id="alert-feed-label")
            yield AlertFeed(id="alert-feed")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Start the orchestrator as a background worker if one is set."""
        if self._orchestrator is not None:
            self.run_worker(
                self._orchestrator.run(),
                exclusive=True,
                group="orchestrator",
                name="orchestrator",
            )
        # Update the clock every second
        self.set_interval(1.0, self._tick_clock)

    def _tick_clock(self) -> None:
        """Refresh the header clock and status bar coin count."""
        now = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
        header = self.query_one("#header", Label)
        header.update(f"HyperSussy  |  {now}")

        status = self.query_one(StatusBar)
        status.coin_count = len(self._seen_coins)
        status.alert_count = self._alert_count

    def on_alert_received(self, message: AlertReceived) -> None:
        """Update status bar last-alert timestamp.

        Args:
            message: The received alert message.
        """
        status = self.query_one(StatusBar)
        status.last_alert_ts = message.alert.timestamp_ms

    async def action_quit(self) -> None:
        """Stop the orchestrator and exit the app."""
        if self._orchestrator is not None:
            self._orchestrator.stop()
        self.exit()
