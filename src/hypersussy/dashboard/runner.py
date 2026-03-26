"""Background thread that runs the async orchestrator alongside Streamlit.

Streamlit's main thread is synchronous; the orchestrator requires asyncio.
BackgroundRunner starts a daemon thread with its own event loop, runs the
orchestrator inside it, and exposes a stop() method for clean shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.config import HyperSussySettings
from hypersussy.dashboard.state import SharedState

logger = logging.getLogger(__name__)


class BackgroundRunner:
    """Manages a daemon thread running the async orchestrator.

    Designed to be instantiated once via @st.cache_resource. The thread
    starts the orchestrator and pushes data into SharedState via the
    DataBus protocol. Calling start() is idempotent.

    Args:
        settings: Application settings.
        shared_state: Shared state that receives snapshots and alerts.
    """

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
        """Launch the daemon thread if not already running.

        Idempotent — safe to call on every Streamlit rerun.
        """
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
        """Signal the orchestrator to stop and join the thread.

        Cancels all running asyncio tasks via the event loop so that
        long-sleeping coroutines are interrupted immediately.
        Blocks until the background thread exits or times out (5s).
        """
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
        """Cancel every pending task in the background event loop.

        Called via call_soon_threadsafe from stop() so it runs in the
        correct thread context.
        """
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
        logger.debug("BackgroundRunner: thread started, creating event loop")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        logger.debug("BackgroundRunner: running _async_main")
        try:
            loop.run_until_complete(self._async_main())
        except asyncio.CancelledError:
            pass  # normal shutdown path via stop()
        except (
            ClientError,
            ServerError,
            requests.RequestException,
            sqlite3.Error,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ):
            logger.exception("BackgroundRunner crashed")
        finally:
            loop.close()
            self._loop = None
            self._state.set_running(False)

    async def _async_main(self) -> None:
        """Wire and run all components inside the background event loop."""
        from hypersussy.alerts.manager import AlertManager
        from hypersussy.alerts.sinks.log_sink import LogSink
        from hypersussy.cli import _build_components, _configure_logging
        from hypersussy.dashboard.sink import StreamlitSink
        from hypersussy.orchestrator import Orchestrator

        db_dir = os.path.dirname(self._settings.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        log_file = os.path.join(db_dir or "data", "hypersussy-dashboard.log")
        _configure_logging(self._settings.log_level, log_file)

        logger.debug("BackgroundRunner: building components")
        reader, stream, storage, engines, _ = _build_components(self._settings)
        logger.debug("BackgroundRunner: initialising storage")
        await storage.init()
        logger.debug("BackgroundRunner: storage ready")

        sinks = [LogSink(), StreamlitSink(self._state)]
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
