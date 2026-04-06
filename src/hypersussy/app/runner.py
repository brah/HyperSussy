"""Background thread that runs the orchestrator alongside the API."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.app.state import SharedState
from hypersussy.config import HyperSussySettings

logger = logging.getLogger(__name__)

# Transient infrastructure failures — expected and recoverable.
_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    ClientError,
    ServerError,
    requests.RequestException,
    sqlite3.Error,
    OSError,
)

# Programming/data errors — indicate bugs; caught only to prevent crashes.
_LOGIC_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    TypeError,
    RuntimeError,
)

_RECOVERABLE = _NETWORK_ERRORS + _LOGIC_ERRORS


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
        self._orchestrator_ref: object | None = None
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
        if self._orchestrator_ref is not None:
            stop_fn = getattr(self._orchestrator_ref, "stop", None)
            if stop_fn is not None:
                stop_fn()
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
        from hypersussy.orchestrator import Orchestrator

        db_dir = os.path.dirname(self._settings.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        log_file = os.path.join(db_dir or "data", "hypersussy-dashboard.log")
        _configure_logging(self._settings.log_level, log_file)
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
        self._orchestrator_ref = orchestrator
        self._state.set_running(True)

        try:
            await orchestrator.run()
        finally:
            await storage.close()
