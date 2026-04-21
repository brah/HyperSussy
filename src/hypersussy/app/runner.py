"""Background thread that runs the orchestrator alongside the API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
from typing import TYPE_CHECKING

from hypersussy.app.state import SharedState
from hypersussy.config import HyperSussySettings
from hypersussy.errors import RECOVERABLE as _RECOVERABLE

if TYPE_CHECKING:
    from hypersussy.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class BackgroundRunner:
    """Manages a daemon thread running the async orchestrator."""

    def __init__(
        self,
        settings: HyperSussySettings,
        shared_state: SharedState,
    ) -> None:
        self._settings = settings
        self._state = shared_state
        self._thread: threading.Thread | None = None
        self._orchestrator: Orchestrator | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Launch the daemon thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            name="hypersussy-orchestrator",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the orchestrator to stop and join the thread."""
        self._stop_event.set()
        if self._orchestrator is not None:
            self._orchestrator.stop()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._cancel_all_tasks)
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _cancel_all_tasks(self) -> None:
        """Cancel every pending task in the background event loop."""
        if self._loop is None:
            return
        for task in asyncio.all_tasks(self._loop):
            task.cancel()

    @property
    def is_alive(self) -> bool:
        """True if the background thread is running."""
        return self._thread is not None and self._thread.is_alive()

    def _run_forever(self) -> None:
        """Thread target: create event loop, run orchestrator, clean up."""
        self._state.clear_runtime_error("background_runner")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_main())
        except asyncio.CancelledError:
            pass
        except _RECOVERABLE as exc:
            self._state.mark_runtime_error("background_runner", str(exc))
            logger.exception("BackgroundRunner crashed")
        finally:
            loop.close()
            self._loop = None
            self._state.set_running(False)

    async def _async_main(self) -> None:
        """Wire and run all components inside the background event loop."""
        from hypersussy.alerts.manager import AlertManager
        from hypersussy.alerts.sinks.log_sink import LogSink
        from hypersussy.app.sink import AppSink
        from hypersussy.cli import _build_components, _configure_logging
        from hypersussy.exchange.hyperliquid.candle_stream import (
            CandleStreamRegistry,
        )
        from hypersussy.orchestrator import Orchestrator

        db_dir = os.path.dirname(self._settings.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        log_file = os.path.join(db_dir or "data", "hypersussy-dashboard.log")
        _configure_logging(
            self._settings.log_level,
            log_file,
            max_bytes=self._settings.log_max_bytes,
            backup_count=self._settings.log_backup_count,
        )
        self._state.set_log_path(log_file)

        reader, stream, storage, engines, _ = _build_components(self._settings)
        await storage.init()
        self._state.clear_runtime_error("background_runner")

        sinks = [LogSink(), AppSink(self._state)]
        alert_manager = AlertManager(
            storage=storage,
            sinks=sinks,
            settings=self._settings,
        )
        orchestrator = Orchestrator(
            reader=reader,
            stream=stream,
            storage=storage,
            engines=engines,
            alert_manager=alert_manager,
            settings=self._settings,
            data_bus=self._state,
        )
        self._orchestrator = orchestrator
        self._state.set_running(True)

        # Live candle stream — runs as a peer task to the orchestrator
        # so the dashboard can push real-time bar updates without
        # polling the REST candles endpoint. Communication with the
        # API layer goes through SharedState's candle methods.
        candle_registry = CandleStreamRegistry(
            ws_url=self._settings.hl_ws_url,
            state=self._state,
        )
        candle_task = asyncio.create_task(
            candle_registry.run(), name="candle_stream_registry"
        )

        try:
            await orchestrator.run()
        finally:
            candle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await candle_task
            await storage.close()
