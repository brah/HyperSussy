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
from collections.abc import Sequence

import requests
from hyperliquid.utils.error import ClientError, ServerError

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
from hypersussy.engines.base import DetectionEngine
from hypersussy.engines.whale_tracker import WhaleTrackerEngine
from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.exchange.hyperliquid.websocket import HyperLiquidStream
from hypersussy.models import Trade
from hypersussy.protocols import DataBus
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)

# HyperLiquid enforces max 10 WS connections per IP.
# 1 connection is reserved for the position WS stream.
_MAX_TRADE_WS_CONNECTIONS = 8
# HL position WS: subscribe up to this many users per connection.
_MAX_POSITION_WS_USERS = 1000

# Exceptions from REST calls, storage, and engine logic that the
# orchestrator must survive without crashing.
_RECOVERABLE: tuple[type[Exception], ...] = (
    ClientError,
    ServerError,
    requests.RequestException,
    sqlite3.Error,
    OSError,
    ValueError,
    KeyError,
    TypeError,
)


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
        self._running = False

    async def run(self) -> None:
        """Start all polling and streaming tasks.

        Runs until cancelled or stop() is called.
        """
        self._running = True
        logger.info("Orchestrator starting...")

        # Fetch initial asset list
        logger.debug("Orchestrator: fetching initial coin list...")
        await self._refresh_coins()
        logger.debug("Orchestrator: coin list ready — %d coins", len(self._coins))

        tasks = [
            asyncio.create_task(self._poll_meta_loop(), name="poll_meta"),
            asyncio.create_task(self._engine_tick_loop(), name="engine_tick"),
            asyncio.create_task(self._refresh_coins_loop(), name="refresh_coins"),
            asyncio.create_task(self._position_stream_loop(), name="position_ws"),
        ]

        # Multiplex trade streams across a limited number of WS connections
        n_conns = min(_MAX_TRADE_WS_CONNECTIONS, len(self._coins))
        if n_conns > 0:
            batch_size = math.ceil(len(self._coins) / n_conns)
            for i in range(n_conns):
                batch = self._coins[i * batch_size : (i + 1) * batch_size]
                if not batch:
                    break
                tasks.append(
                    asyncio.create_task(
                        self._trade_stream_batch(batch),
                        name=f"trades_ws_{i}",
                    )
                )

        logger.info(
            "Orchestrator running with %d coins across %d WS connections, %d engines",
            len(self._coins),
            n_conns,
            len(self._engines),
        )

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Orchestrator shutting down...")
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the orchestrator to stop."""
        self._running = False

    async def _refresh_coins(self) -> None:
        """Fetch the current list of perpetual assets."""
        snapshots = await self._reader.get_asset_snapshots()
        if self._settings.watched_coins:
            self._coins = [
                s.coin for s in snapshots if s.coin in self._settings.watched_coins
            ]
        else:
            self._coins = [s.coin for s in snapshots]
        logger.info("Tracking %d coins", len(self._coins))

    async def _refresh_coins_loop(self) -> None:
        """Periodically refresh the asset list for new listings."""
        while self._running:
            await asyncio.sleep(self._settings.asset_list_refresh_s)
            try:
                await self._refresh_coins()
            except _RECOVERABLE:
                logger.exception("Failed to refresh coin list")

    async def _poll_meta_loop(self) -> None:
        """Poll metaAndAssetCtxs and dispatch to engines."""
        while self._running:
            try:
                snapshots = await self._reader.get_asset_snapshots()
                await self._storage.insert_asset_snapshots(snapshots)

                for snapshot in snapshots:
                    if self._data_bus is not None:
                        self._data_bus.push_snapshot(snapshot)
                    for engine in self._engines:
                        alerts = await engine.on_asset_update(snapshot)
                        for alert in alerts:
                            await self._alert_manager.process_alert(alert)
            except _RECOVERABLE:
                logger.exception("Error in meta polling loop")

            await asyncio.sleep(self._settings.meta_poll_interval_s)

    async def _engine_tick_loop(self) -> None:
        """Periodically call tick() on all engines."""
        while self._running:
            now_ms = int(time.time() * 1000)
            for engine in self._engines:
                try:
                    alerts = await engine.tick(now_ms)
                    for alert in alerts:
                        await self._alert_manager.process_alert(alert)
                except _RECOVERABLE:
                    logger.exception("Error in engine tick: %s", engine.name)
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
        async for trade in self._stream.stream_trades_multi(coins):
            if not self._running:
                break
            await self._dispatch_trade(trade)

    async def _position_stream_loop(self) -> None:
        """Stream real-time position updates for all tracked whale addresses.

        Subscribes to ``clearinghouseState`` for every tracked whale on a
        single WS connection, yielding parsed positions to
        ``WhaleTrackerEngine.on_position_update``.  Restarts from storage
        each time the connection is (re-)established so that newly
        discovered whales are picked up automatically.
        """
        whale_engines = [e for e in self._engines if isinstance(e, WhaleTrackerEngine)]
        if not whale_engines:
            logger.debug("_position_stream_loop: no whale engines — exiting")
            return
        logger.debug("_position_stream_loop: %d whale engine(s)", len(whale_engines))
        while self._running:
            logger.debug("_position_stream_loop: fetching tracked addresses")
            tracked = await self._storage.get_tracked_addresses()
            logger.debug("_position_stream_loop: %d tracked addresses", len(tracked))
            if not tracked:
                await asyncio.sleep(10.0)
                continue
            users = tracked[:_MAX_POSITION_WS_USERS]
            logger.info("Starting position WS stream for %d addresses", len(users))
            try:
                async for (
                    address,
                    positions,
                ) in self._stream.stream_clearinghouse_states(users):
                    if not self._running:
                        break
                    now_ms = int(time.time() * 1000)
                    for engine in whale_engines:
                        try:
                            pos_alerts = await engine.on_position_update(
                                address, positions, now_ms
                            )
                            for alert in pos_alerts:
                                await self._alert_manager.process_alert(alert)
                        except _RECOVERABLE:
                            logger.exception(
                                "Error in on_position_update for %s", address
                            )
            except _RECOVERABLE:
                logger.exception("Position stream loop error; restarting")
                await asyncio.sleep(2)

    async def _dispatch_trade(self, trade: Trade) -> None:
        """Fan out a trade to storage and all engines.

        Args:
            trade: The incoming trade.
        """
        try:
            await self._storage.insert_trades([trade])
        except _RECOVERABLE:
            logger.exception("Failed to store trade")

        for engine in self._engines:
            try:
                alerts = await engine.on_trade(trade)
                for alert in alerts:
                    await self._alert_manager.process_alert(alert)
            except _RECOVERABLE:
                logger.exception(
                    "Error dispatching trade to engine %s",
                    engine.name,
                )
