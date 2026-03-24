"""Central orchestrator coordinating polling, streaming, and engines.

Manages the main async event loop that ties together data collection,
engine dispatch, and alert routing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
from hypersussy.engines.base import DetectionEngine
from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.exchange.hyperliquid.websocket import HyperLiquidStream
from hypersussy.models import Trade
from hypersussy.storage.base import StorageProtocol

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._reader = reader
        self._stream = stream
        self._storage = storage
        self._engines = engines
        self._alert_manager = alert_manager
        self._settings = settings
        self._coins: list[str] = []
        self._running = False

    async def run(self) -> None:
        """Start all polling and streaming tasks.

        Runs until cancelled or stop() is called.
        """
        self._running = True
        logger.info("Orchestrator starting...")

        # Fetch initial asset list
        await self._refresh_coins()

        tasks = [
            asyncio.create_task(self._poll_meta_loop(), name="poll_meta"),
            asyncio.create_task(self._engine_tick_loop(), name="engine_tick"),
            asyncio.create_task(self._refresh_coins_loop(), name="refresh_coins"),
        ]

        # Start trade streams for all coins
        for coin in self._coins:
            tasks.append(
                asyncio.create_task(
                    self._trade_stream_task(coin),
                    name=f"trades_{coin}",
                )
            )

        logger.info(
            "Orchestrator running with %d coins, %d engines",
            len(self._coins),
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
            except Exception:
                logger.exception("Failed to refresh coin list")

    async def _poll_meta_loop(self) -> None:
        """Poll metaAndAssetCtxs and dispatch to engines."""
        while self._running:
            try:
                snapshots = await self._reader.get_asset_snapshots()
                await self._storage.insert_asset_snapshots(snapshots)

                for snapshot in snapshots:
                    for engine in self._engines:
                        alerts = await engine.on_asset_update(snapshot)
                        for alert in alerts:
                            await self._alert_manager.process_alert(alert)
            except Exception:
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
                except Exception:
                    logger.exception("Error in engine tick: %s", engine.name)
            await asyncio.sleep(self._settings.meta_poll_interval_s)

    async def _trade_stream_task(self, coin: str) -> None:
        """Stream trades for a single coin and dispatch.

        Args:
            coin: Asset name to stream.
        """
        logger.info("Starting trade stream for %s", coin)
        async for trade in self._stream.stream_trades(coin):
            if not self._running:
                break
            await self._dispatch_trade(trade)

    async def _dispatch_trade(self, trade: Trade) -> None:
        """Fan out a trade to storage and all engines.

        Args:
            trade: The incoming trade.
        """
        try:
            await self._storage.insert_trades([trade])
        except Exception:
            logger.exception("Failed to store trade")

        for engine in self._engines:
            try:
                alerts = await engine.on_trade(trade)
                for alert in alerts:
                    await self._alert_manager.process_alert(alert)
            except Exception:
                logger.exception(
                    "Error dispatching trade to engine %s",
                    engine.name,
                )
