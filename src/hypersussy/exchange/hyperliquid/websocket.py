"""Async WebSocket manager for HyperLiquid real-time streams.

Uses the ``websockets`` library directly (not the SDK's thread-based
WebsocketManager) for full async compatibility with the orchestrator's
event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
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

_APP_PING_INTERVAL_S = 50  # Match SDK: application-level {"method":"ping"}
_RECONNECT_DELAY_S = 2
_MAX_RECONNECT_DELAY_S = 60


class WsThrottle:
    """Rate-limits WebSocket connections and subscribe messages.

    Uses asyncio locks to serialize concurrent callers and enforce
    minimum delays between operations, preventing bursts that trigger
    HyperLiquid's "Too many errors" protection.

    Args:
        connect_delay_s: Minimum seconds between new WS connections.
        subscribe_delay_s: Minimum seconds between subscribe messages.
    """

    def __init__(
        self,
        connect_delay_s: float = 2.5,
        subscribe_delay_s: float = 0.05,
    ) -> None:
        self.connect_delay_s = connect_delay_s
        self.subscribe_delay_s = subscribe_delay_s
        self._connect_lock = asyncio.Lock()
        self._subscribe_lock = asyncio.Lock()
        self._last_connect: float = 0.0
        self._last_subscribe: float = 0.0

    async def wait_connect(self) -> None:
        """Wait until it is safe to open a new connection."""
        async with self._connect_lock:
            elapsed = time.monotonic() - self._last_connect
            if elapsed < self.connect_delay_s:
                await asyncio.sleep(self.connect_delay_s - elapsed)
            self._last_connect = time.monotonic()

    async def wait_subscribe(self) -> None:
        """Wait until it is safe to send a subscribe message."""
        async with self._subscribe_lock:
            elapsed = time.monotonic() - self._last_subscribe
            if elapsed < self.subscribe_delay_s:
                await asyncio.sleep(self.subscribe_delay_s - elapsed)
            self._last_subscribe = time.monotonic()


class HyperLiquidStream:
    """Async WebSocket client for HyperLiquid real-time data.

    Args:
        ws_url: WebSocket endpoint URL.
        throttle: Shared throttle for connection/subscribe pacing.
    """

    def __init__(
        self,
        ws_url: str = "wss://api.hyperliquid.xyz/ws",
        throttle: WsThrottle | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._throttle = throttle or WsThrottle()

    async def _connect(self) -> ClientConnection:
        """Establish a WebSocket connection.

        Returns:
            Connected WebSocket client.
        """
        await self._throttle.wait_connect()
        return await websockets.connect(
            self._ws_url,
            ping_interval=None,  # Disable protocol-level pings; HL uses app-level
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
        await self._throttle.wait_subscribe()
        msg = orjson.dumps({"method": "subscribe", "subscription": subscription})
        await ws.send(msg.decode("utf-8"))

    @staticmethod
    async def _ping_loop(ws: ClientConnection) -> None:
        """Send application-level pings to keep the connection alive.

        HyperLiquid expects ``{"method": "ping"}`` JSON messages
        (not WebSocket protocol-level pings).

        Args:
            ws: Active WebSocket connection.
        """
        try:
            while True:
                await asyncio.sleep(_APP_PING_INTERVAL_S)
                await ws.send('{"method":"ping"}')
        except (
            websockets.ConnectionClosed,
            asyncio.CancelledError,
        ):
            pass

    @staticmethod
    def _parse_ws_message(raw_msg: str | bytes) -> dict[str, Any] | None:
        """Parse an incoming WebSocket message as JSON.

        Gracefully handles non-JSON messages such as the
        ``"Websocket connection established."`` greeting.

        Args:
            raw_msg: Raw message from the WebSocket.

        Returns:
            Parsed dict, or None if the message is not valid JSON.
        """
        try:
            if isinstance(raw_msg, bytes):
                result: dict[str, Any] = orjson.loads(raw_msg)
            else:
                result = orjson.loads(raw_msg.encode("utf-8"))
            return result
        except orjson.JSONDecodeError:
            logger.debug("Non-JSON WS message: %s", raw_msg[:120])
            return None

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
                ping_task = asyncio.create_task(self._ping_loop(ws))
                try:
                    await self._subscribe(ws, subscription)
                    delay = _RECONNECT_DELAY_S
                    async for raw_msg in ws:
                        data = self._parse_ws_message(raw_msg)
                        if data is None:
                            continue
                        channel = data.get("channel")
                        if channel in ("pong", "subscriptionResponse"):
                            continue
                        if channel == subscription.get("type") or channel == "trades":
                            yield data
                finally:
                    ping_task.cancel()
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

    async def stream_trades_multi(self, coins: list[str]) -> AsyncIterator[Trade]:
        """Yield trades for multiple coins on a single WS connection.

        Sends one ``subscribe`` per coin, then yields all incoming
        trades.  This avoids opening one connection per coin, which
        quickly hits the HyperLiquid 10-connection limit.

        Args:
            coins: Asset names to subscribe to.

        Yields:
            Each trade as it occurs, with buyer/seller addresses.
        """
        delay = _RECONNECT_DELAY_S
        while True:
            try:
                ws = await self._connect()
                ping_task = asyncio.create_task(self._ping_loop(ws))
                try:
                    for coin in coins:
                        await self._subscribe(ws, {"type": "trades", "coin": coin})
                    delay = _RECONNECT_DELAY_S
                    async for raw_msg in ws:
                        data = self._parse_ws_message(raw_msg)
                        if data is None:
                            continue
                        channel = data.get("channel")
                        if channel in ("pong", "subscriptionResponse"):
                            continue
                        if channel == "trades":
                            for trade in parse_ws_trades(data):
                                yield trade
                finally:
                    ping_task.cancel()
                    await ws.close()
            except (
                websockets.ConnectionClosed,
                websockets.InvalidURI,
                OSError,
            ) as exc:
                logger.warning(
                    "WebSocket disconnected (%d coins): %s. Reconnecting in %ds...",
                    len(coins),
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY_S)

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
