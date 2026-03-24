"""Async WebSocket manager for HyperLiquid real-time streams.

Uses the ``websockets`` library directly (not the SDK's thread-based
WebsocketManager) for full async compatibility with the orchestrator's
event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import orjson
import websockets
from websockets.asyncio.client import ClientConnection

from hypersussy.exchange.hyperliquid.parsers import (
    parse_ws_all_mids,
    parse_ws_trades,
)
from hypersussy.models import L2Book, Trade

logger = logging.getLogger(__name__)

_PING_INTERVAL_S = 20
_RECONNECT_DELAY_S = 2
_MAX_RECONNECT_DELAY_S = 60


class HyperLiquidStream:
    """Async WebSocket client for HyperLiquid real-time data.

    Args:
        ws_url: WebSocket endpoint URL.
    """

    def __init__(
        self,
        ws_url: str = "wss://api.hyperliquid.xyz/ws",
    ) -> None:
        self._ws_url = ws_url

    async def _connect(self) -> ClientConnection:
        """Establish a WebSocket connection.

        Returns:
            Connected WebSocket client.
        """
        return await websockets.connect(
            self._ws_url,
            ping_interval=_PING_INTERVAL_S,
            max_size=10 * 1024 * 1024,
        )

    async def _subscribe(
        self,
        ws: ClientConnection,
        subscription: dict[str, Any],
    ) -> None:
        """Send a subscription message.

        Args:
            ws: Active WebSocket connection.
            subscription: Subscription payload dict.
        """
        msg = orjson.dumps({"method": "subscribe", "subscription": subscription})
        await ws.send(msg)

    async def _iter_messages(
        self,
        subscription: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Connect, subscribe, and yield parsed messages with reconnection.

        Args:
            subscription: The subscription payload.

        Yields:
            Parsed JSON message dicts from the channel.
        """
        delay = _RECONNECT_DELAY_S
        while True:
            try:
                ws = await self._connect()
                try:
                    await self._subscribe(ws, subscription)
                    delay = _RECONNECT_DELAY_S
                    async for raw_msg in ws:
                        if isinstance(raw_msg, bytes):
                            data = orjson.loads(raw_msg)
                        else:
                            data = orjson.loads(raw_msg.encode("utf-8"))
                        channel = data.get("channel")
                        if channel == "pong":
                            continue
                        if channel == subscription.get("type") or channel == "trades":
                            yield data
                finally:
                    await ws.close()
            except (
                websockets.ConnectionClosed,
                websockets.InvalidURI,
                OSError,
            ) as exc:
                logger.warning(
                    "WebSocket disconnected: %s. Reconnecting in %ds...",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY_S)

    async def stream_trades(self, coin: str) -> AsyncIterator[Trade]:
        """Yield trades in real time for a coin.

        Args:
            coin: Asset name (e.g. "BTC").

        Yields:
            Each trade as it occurs, with buyer/seller addresses.
        """
        sub = {"type": "trades", "coin": coin}
        async for msg in self._iter_messages(sub):
            for trade in parse_ws_trades(msg):
                yield trade

    async def stream_all_mids(
        self,
    ) -> AsyncIterator[dict[str, float]]:
        """Yield mid-price updates for all assets.

        Yields:
            Dict mapping coin name to mid price.
        """
        sub = {"type": "allMids"}
        async for msg in self._iter_messages(sub):
            yield parse_ws_all_mids(msg)

    async def stream_l2_book(self, coin: str) -> AsyncIterator[L2Book]:
        """Yield L2 book updates for a coin.

        Args:
            coin: Asset name.

        Yields:
            Updated L2 book snapshots.
        """
        sub = {"type": "l2Book", "coin": coin}
        async for msg in self._iter_messages(sub):
            data = msg.get("data", {})
            levels = data.get("levels", [[], []])
            bids = tuple((float(lvl["px"]), float(lvl["sz"])) for lvl in levels[0])
            asks = tuple((float(lvl["px"]), float(lvl["sz"])) for lvl in levels[1])
            yield L2Book(
                coin=data.get("coin", coin),
                timestamp_ms=data.get(
                    "time", int(asyncio.get_event_loop().time() * 1000)
                ),
                bids=bids,
                asks=asks,
            )
