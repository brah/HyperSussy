"""Central orchestrator coordinating polling, streaming, and engines.

Manages the main async event loop that ties together data collection,
engine dispatch, and alert routing.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sqlite3
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from functools import partial

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
from hypersussy.engines.base import DetectionEngine
from hypersussy.engines.whale_tracker import WhaleTrackerEngine
from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.exchange.hyperliquid.websocket import HyperLiquidStream
from hypersussy.logging_utils import LogFloodGuard
from hypersussy.models import Alert, Trade
from hypersussy.protocols import DataBus
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)

# HyperLiquid enforces max 10 WS connections per IP.
# 1 connection reserved for position WS, 1 for asset ctx WS.
_MAX_TRADE_WS_CONNECTIONS = 7
# HL position WS: subscribe up to this many users per connection.
_MAX_POSITION_WS_USERS = 1000
# Periodic reconciliation cadence for dynamic market stream subscriptions.
_STREAM_RECONCILE_S = 1.0

# Transient infrastructure failures — expected and recoverable.
_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    ClientError,
    ServerError,
    requests.RequestException,
    sqlite3.Error,
    OSError,
)

# Programming/data errors — indicate bugs; caught only to prevent
# daemon crashes. Each occurrence should be investigated.
_LOGIC_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    TypeError,
)

_RECOVERABLE = _NETWORK_ERRORS + _LOGIC_ERRORS


class Orchestrator:
    """Main coordinator for data collection and engine dispatch.

    Args:
        reader: REST client for periodic polling.
        stream: WebSocket client for real-time data.
        storage: Persistent storage backend.
        engines: Detection engines to dispatch events to.
        alert_manager: Alert processing pipeline.
        settings: Application settings.
    """

    def __init__(
        self,
        reader: HyperLiquidReader,
        stream: HyperLiquidStream,
        storage: StorageProtocol,
        engines: Sequence[DetectionEngine],
        alert_manager: AlertManager,
        settings: HyperSussySettings,
        data_bus: DataBus | None = None,
    ) -> None:
        self._reader = reader
        self._stream = stream
        self._storage = storage
        self._engines = engines
        self._alert_manager = alert_manager
        self._settings = settings
        self._data_bus = data_bus
        self._coins: list[str] = []
        self._native_coins: list[str] = []
        self._running = False
        self._log_guard = LogFloodGuard(window_s=60.0)
        self._trade_storage_backoff_until = 0.0
        self._trade_storage_failures = 0
        self._trade_buffer: deque[Trade] = deque(maxlen=50_000)

    def _mark_engine_error(self, engine_name: str, exc: Exception) -> None:
        """Forward engine errors to the dashboard state when available."""
        if self._data_bus is None:
            return
        mark = getattr(self._data_bus, "mark_engine_error", None)
        if callable(mark):
            mark(engine_name, str(exc))

    def _clear_engine_error(self, engine_name: str) -> None:
        """Clear a previously recorded engine error."""
        if self._data_bus is None:
            return
        clear = getattr(self._data_bus, "clear_engine_error", None)
        if callable(clear):
            clear(engine_name)

    def _mark_runtime_error(self, source: str, exc: Exception) -> None:
        """Forward runtime loop errors to the dashboard state when available."""
        if self._data_bus is None:
            return
        mark = getattr(self._data_bus, "mark_runtime_error", None)
        if callable(mark):
            mark(source, str(exc))

    def _clear_runtime_error(self, source: str) -> None:
        """Clear a previously recorded runtime error."""
        if self._data_bus is None:
            return
        clear = getattr(self._data_bus, "clear_runtime_error", None)
        if callable(clear):
            clear(source)

    async def _dispatch_alerts(self, alerts: list[Alert]) -> None:
        """Process a batch of alerts through the alert manager."""
        for alert in alerts:
            await self._alert_manager.process_alert(alert)

    async def _run_engine_call(
        self,
        engine: DetectionEngine,
        call: Callable[[], Awaitable[list[Alert]]],
        failure_message: str,
        *failure_args: object,
    ) -> None:
        """Run one engine callback with shared error handling."""
        try:
            alerts = await call()
            self._clear_engine_error(engine.name)
            await self._dispatch_alerts(alerts)
        except _RECOVERABLE as exc:
            self._mark_engine_error(engine.name, exc)
            logger.exception(failure_message, *failure_args)

    async def run(self) -> None:
        """Start all polling and streaming tasks.

        Runs until cancelled or stop() is called.
        """
        self._running = True
        logger.info("Orchestrator starting...")

        await self._refresh_coins()
        trade_batches = self._trade_batches(self._coins)

        tasks = [
            asyncio.create_task(self._poll_meta_loop(), name="poll_meta"),
            asyncio.create_task(self._engine_tick_loop(), name="engine_tick"),
            asyncio.create_task(self._refresh_coins_loop(), name="refresh_coins"),
            asyncio.create_task(self._position_stream_loop(), name="position_ws"),
            asyncio.create_task(
                self._trade_stream_supervisor_loop(),
                name="trade_ws_supervisor",
            ),
            asyncio.create_task(
                self._asset_ctx_stream_supervisor_loop(),
                name="asset_ctx_supervisor",
            ),
        ]

        logger.info(
            "Orchestrator running with %d coins (%d native via WS)"
            " across %d WS connections, %d engines",
            len(self._coins),
            len(self._native_coins),
            len(trade_batches),
            len(self._engines),
        )

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Orchestrator shutting down...")
            raise
        finally:
            self._running = False
            await self._cancel_tasks(tasks)

    def stop(self) -> None:
        """Signal the orchestrator to stop."""
        self._running = False

    async def _refresh_coins(self) -> None:
        """Fetch the current list of perpetual assets."""
        snapshots = await self._reader.get_asset_snapshots()
        self._clear_runtime_error("refresh_coins")
        all_coins = [s.coin for s in snapshots]
        if self._settings.watched_coins:
            all_coins = [c for c in all_coins if c in self._settings.watched_coins]

        native_coins = [c for c in all_coins if ":" not in c]
        changed = all_coins != self._coins or native_coins != self._native_coins
        self._coins = all_coins
        self._native_coins = native_coins
        logger.info(
            "Tracking %d coins (%d native, %d HIP-3)",
            len(self._coins),
            len(self._native_coins),
            len(self._coins) - len(self._native_coins),
        )
        if changed:
            logger.info("Coin universe changed; live stream subscriptions will refresh")

    async def _refresh_coins_loop(self) -> None:
        """Periodically refresh the asset list for new listings."""
        while self._running:
            await asyncio.sleep(self._settings.asset_list_refresh_s)
            try:
                await self._refresh_coins()
                self._clear_runtime_error("refresh_coins")
            except _RECOVERABLE as exc:
                self._mark_runtime_error("refresh_coins", exc)
                logger.exception("Failed to refresh coin list")

    async def _poll_meta_loop(self) -> None:
        """Poll metaAndAssetCtxs for bulk storage and HIP-3 engine dispatch.

        Native coin engine dispatch is handled in real time by
        ``_asset_ctx_stream_loop``; this loop dispatches only HIP-3
        coins (identified by the ``dex:COIN`` naming convention) and
        stores all snapshots to SQLite at each poll interval.
        """
        while self._running:
            try:
                snapshots = await self._reader.get_asset_snapshots()
                await self._storage.insert_asset_snapshots(snapshots)
                for snapshot in snapshots:
                    if ":" not in snapshot.coin:
                        continue  # native coins dispatched via WS stream
                    if self._data_bus is not None:
                        self._data_bus.push_snapshot(snapshot)
                    for engine in self._engines:
                        await self._run_engine_call(
                            engine,
                            partial(engine.on_asset_update, snapshot),
                            "Error in on_asset_update (meta polling) for %s",
                            snapshot.coin,
                        )
                self._clear_runtime_error("poll_meta")
            except _RECOVERABLE as exc:
                self._mark_runtime_error("poll_meta", exc)
                logger.exception("Error in meta polling loop")

            await asyncio.sleep(self._settings.meta_poll_interval_s)

    async def _asset_ctx_stream_loop(self, coins: list[str]) -> None:
        """Stream activeAssetCtx updates for native perpetual coins.

        Dispatches each snapshot to engines and the data bus in real time.
        Storage is handled separately by ``_poll_meta_loop``.

        Args:
            coins: Native perpetual asset names (no ``:`` in name).
        """
        logger.info("Starting asset ctx WS stream for %d native coins", len(coins))
        try:
            async for snapshot in self._stream.stream_asset_ctxs(coins):
                if not self._running:
                    break
                if self._data_bus is not None:
                    self._data_bus.push_snapshot(snapshot)
                for engine in self._engines:
                    await self._run_engine_call(
                        engine,
                        partial(engine.on_asset_update, snapshot),
                        "Error in on_asset_update (asset ctx stream) for %s",
                        snapshot.coin,
                    )
            self._clear_runtime_error("asset_ctx_stream")
        except _RECOVERABLE as exc:
            self._mark_runtime_error("asset_ctx_stream", exc)
            logger.exception("Asset ctx stream loop error")

    async def _engine_tick_loop(self) -> None:
        """Periodically call tick() on all engines."""
        while self._running:
            now_ms = int(time.time() * 1000)
            for engine in self._engines:
                await self._run_engine_call(
                    engine,
                    partial(engine.tick, now_ms),
                    "Error in engine tick: %s",
                    engine.name,
                )
            await asyncio.sleep(self._settings.engine_tick_interval_s)

    async def _trade_stream_batch(self, coins: list[str]) -> None:
        """Stream trades for a batch of coins on one WS connection.

        Args:
            coins: Asset names to subscribe to on this connection.
        """
        logger.info(
            "Starting multiplexed trade stream for %d coins: %s",
            len(coins),
            ", ".join(coins[:5]) + ("..." if len(coins) > 5 else ""),
        )
        try:
            async for trade in self._stream.stream_trades_multi(coins):
                if not self._running:
                    break
                await self._dispatch_trade(trade)
            self._clear_runtime_error("trade_stream")
        except _RECOVERABLE as exc:
            self._mark_runtime_error("trade_stream", exc)
            logger.exception("Trade stream loop error")

    @staticmethod
    async def _cancel_tasks(tasks: list[asyncio.Task[None]]) -> None:
        """Cancel and await a set of background tasks."""
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _log_failed_stream_tasks(
        self,
        tasks: list[asyncio.Task[None]],
        stream_name: str,
    ) -> bool:
        """Log failures from completed stream tasks and signal a restart."""
        needs_restart = False
        for task in tasks:
            if not task.done():
                continue
            needs_restart = True
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                if isinstance(exc, Exception):
                    self._mark_runtime_error(stream_name, exc)
                logger.error("%s task crashed; restarting", stream_name, exc_info=exc)
        return needs_restart

    @staticmethod
    def _trade_batches(coins: Sequence[str]) -> list[list[str]]:
        """Split tracked coins across the allowed number of trade WS connections."""
        if not coins:
            return []
        n_conns = min(_MAX_TRADE_WS_CONNECTIONS, len(coins))
        batch_size = math.ceil(len(coins) / n_conns)
        return [
            list(coins[i : i + batch_size]) for i in range(0, len(coins), batch_size)
        ]

    async def _trade_stream_supervisor_loop(self) -> None:
        """Keep trade stream subscriptions aligned with the current coin universe."""
        active_batches: tuple[tuple[str, ...], ...] = ()
        tasks: list[asyncio.Task[None]] = []
        try:
            while self._running:
                if self._log_failed_stream_tasks(tasks, "trade stream"):
                    await self._cancel_tasks(tasks)
                    tasks = []
                    active_batches = ()

                desired_batches = tuple(
                    tuple(batch) for batch in self._trade_batches(self._coins)
                )
                if desired_batches != active_batches:
                    await self._cancel_tasks(tasks)
                    tasks = [
                        asyncio.create_task(
                            self._trade_stream_batch(list(batch)),
                            name=f"trades_ws_{idx}",
                        )
                        for idx, batch in enumerate(desired_batches)
                    ]
                    active_batches = desired_batches
                    logger.info(
                        "Trade WS subscriptions refreshed across %d connection(s)",
                        len(desired_batches),
                    )
                    self._clear_runtime_error("trade stream")
                await asyncio.sleep(_STREAM_RECONCILE_S)
        finally:
            await self._cancel_tasks(tasks)

    async def _asset_ctx_stream_supervisor_loop(self) -> None:
        """Keep native asset-context streaming aligned with native coins."""
        active_coins: tuple[str, ...] = ()
        task: asyncio.Task[None] | None = None
        try:
            while self._running:
                task_list = [task] if task is not None else []
                if self._log_failed_stream_tasks(task_list, "asset ctx stream"):
                    await self._cancel_tasks(task_list)
                    task = None
                    active_coins = ()

                desired_coins = tuple(self._native_coins)
                if desired_coins != active_coins:
                    await self._cancel_tasks(task_list)
                    task = (
                        asyncio.create_task(
                            self._asset_ctx_stream_loop(list(desired_coins)),
                            name="asset_ctx_ws",
                        )
                        if desired_coins
                        else None
                    )
                    active_coins = desired_coins
                    logger.info(
                        "Asset ctx WS subscriptions refreshed for %d native coin(s)",
                        len(desired_coins),
                    )
                    self._clear_runtime_error("asset ctx stream")
                await asyncio.sleep(_STREAM_RECONCILE_S)
        finally:
            await self._cancel_tasks([task] if task is not None else [])

    async def _position_stream_loop(self) -> None:
        """Stream real-time position updates for all tracked whale addresses.

        Subscribes to ``clearinghouseState`` for every tracked whale on a
        single WS connection, yielding parsed positions to
        ``WhaleTrackerEngine.on_position_update``. Restarts from storage
        each time the connection is (re-)established so that newly
        discovered whales are picked up automatically.
        """
        whale_engines = [e for e in self._engines if isinstance(e, WhaleTrackerEngine)]
        if not whale_engines:
            logger.debug("_position_stream_loop: no whale engines exiting")
            return
        logger.debug("_position_stream_loop: %d whale engine(s)", len(whale_engines))
        while self._running:
            logger.debug("_position_stream_loop: fetching tracked addresses")
            try:
                tracked = await self._storage.get_tracked_addresses()
                self._clear_runtime_error("position_stream")
            except _RECOVERABLE as exc:
                self._mark_runtime_error("position_stream", exc)
                logger.exception(
                    "Failed to fetch tracked addresses for position stream"
                )
                await asyncio.sleep(2)
                continue
            logger.debug("_position_stream_loop: %d tracked addresses", len(tracked))
            if not tracked:
                await asyncio.sleep(10.0)
                continue
            users = tracked[:_MAX_POSITION_WS_USERS]
            logger.info("Starting position WS stream for %d addresses", len(users))
            try:
                position_stream = self._stream.stream_clearinghouse_states(users)
                async for address, positions in position_stream:
                    if not self._running:
                        break
                    now_ms = int(time.time() * 1000)
                    for engine in whale_engines:
                        await self._run_engine_call(
                            engine,
                            partial(
                                engine.on_position_update,
                                address,
                                positions,
                                now_ms,
                            ),
                            "Error in on_position_update for %s",
                            address,
                        )
                self._clear_runtime_error("position_stream")
            except _RECOVERABLE as exc:
                self._mark_runtime_error("position_stream", exc)
                logger.exception("Position stream loop error; restarting")
                await asyncio.sleep(2)

    async def _dispatch_trade(self, trade: Trade) -> None:
        """Fan out a trade to storage and all engines.

        Trades that arrive during a storage backoff window are buffered
        and flushed on the next successful write, preventing permanent
        gaps in the trades table from transient DB issues.

        Args:
            trade: The incoming trade.
        """
        now = time.monotonic()
        if now >= self._trade_storage_backoff_until:
            self._trade_buffer.append(trade)
            await self._flush_trade_buffer()
        else:
            self._trade_buffer.append(trade)

        for engine in self._engines:
            await self._run_engine_call(
                engine,
                partial(engine.on_trade, trade),
                "Error dispatching trade to engine %s",
                engine.name,
            )

    async def _flush_trade_buffer(self) -> None:
        """Attempt to write all buffered trades to storage."""
        if not self._trade_buffer:
            return
        batch = list(self._trade_buffer)
        try:
            await self._storage.insert_trades(batch)
            self._trade_buffer.clear()
            self._trade_storage_failures = 0
            self._trade_storage_backoff_until = 0.0
            self._clear_runtime_error("trade_storage")
        except _RECOVERABLE as exc:
            self._mark_runtime_error("trade_storage", exc)
            self._trade_storage_failures += 1
            delay = min(30.0, 2 ** min(self._trade_storage_failures - 1, 5))
            self._trade_storage_backoff_until = time.monotonic() + delay
            is_db_lock = isinstance(exc, sqlite3.OperationalError) and (
                "locked" in str(exc).lower()
            )
            self._log_guard.log(
                logger,
                logging.WARNING if is_db_lock else logging.ERROR,
                (
                    "trade_storage_locked"
                    if is_db_lock
                    else f"trade_storage:{type(exc).__name__}"
                ),
                "Trade storage unavailable (%d buffered); retrying in %.1fs (%s)",
                len(self._trade_buffer),
                delay,
                exc,
                exc_info=not is_db_lock,
            )
