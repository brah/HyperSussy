"""Async WebSocket manager for HyperLiquid real-time streams.

Uses the ``websockets`` library directly (not the SDK's thread-based
WebsocketManager) for full async compatibility with the orchestrator's
event loop. Protocol-level primitives (ping interval, reconnect
backoff, JSON parsing, disconnect-error tuple) live in
:mod:`hypersussy.exchange.hyperliquid._ws_common` so the candle
stream registry can share them without copy-paste.
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

from hypersussy.exchange.hyperliquid._ws_common import (
    DISCONNECT_ERRORS,
    MAX_RECONNECT_DELAY_S,
    RECONNECT_DELAY_S,
    parse_ws_message,
    ping_loop,
)
from hypersussy.exchange.hyperliquid.parsers import (
    parse_l2_snapshot,
    parse_user_state,
    parse_ws_active_asset_ctx,
    parse_ws_all_mids,
    parse_ws_trades,
)
from hypersussy.models import AssetSnapshot, L2Book, Position, Trade

logger = logging.getLogger(__name__)


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

    async def _send_subscribe(
        self,
        ws: ClientConnection,
        subscription: dict[str, Any],
        *,
        throttle: bool,
    ) -> None:
        """Send a single subscribe frame.

        Args:
            ws: Active WebSocket connection.
            subscription: Subscription payload dict.
            throttle: When True, wait on the shared subscribe lock;
                when False, write the frame directly. The clearing-
                house-state stream bypasses throttling because holding
                the global lock for N user subscribes would stall the
                trade stream's coin subscribes on other connections.
        """
        if throttle:
            await self._throttle.wait_subscribe()
        msg = orjson.dumps({"method": "subscribe", "subscription": subscription})
        await ws.send(msg.decode("utf-8"))

    async def _iter_subscription(
        self,
        subscriptions: list[dict[str, Any]],
        expected_channel: str,
        *,
        log_label: str,
        throttle_subscribes: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """Connect, subscribe, and yield matching messages with reconnect.

        One method replaces what used to be three near-identical read
        loops (single-sub, multi-sub, and a bespoke clearinghouse
        variant with its own throttle bypass). The differences were
        mechanical: number of subscribe frames, which channel to
        keep, whether each subscribe waits on the global throttle.

        Args:
            subscriptions: List of subscription payloads to send on
                every reconnect. Order is preserved.
            expected_channel: Only messages whose ``channel`` field
                equals this string are yielded. HL's control frames
                (``pong``, ``subscriptionResponse``) are always
                dropped regardless.
            log_label: Prefix for the reconnect warning log line.
            throttle_subscribes: See :meth:`_send_subscribe`.
        """
        delay = RECONNECT_DELAY_S
        while True:
            try:
                ws = await self._connect()
                ping_task = asyncio.create_task(ping_loop(ws))
                try:
                    for sub in subscriptions:
                        await self._send_subscribe(
                            ws, sub, throttle=throttle_subscribes
                        )
                    delay = RECONNECT_DELAY_S
                    async for raw_msg in ws:
                        data = parse_ws_message(raw_msg)
                        if data is None:
                            continue
                        channel = data.get("channel")
                        if channel in ("pong", "subscriptionResponse"):
                            continue
                        if channel == expected_channel:
                            yield data
                finally:
                    ping_task.cancel()
                    await ws.close()
            except DISCONNECT_ERRORS as exc:
                logger.warning(
                    "%s disconnected (%d sub(s)): %s. Reconnecting in %ds...",
                    log_label,
                    len(subscriptions),
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY_S)

    async def stream_trades(self, coin: str) -> AsyncIterator[Trade]:
        """Yield trades in real time for a coin.

        Args:
            coin: Asset name (e.g. "BTC").

        Yields:
            Each trade as it occurs, with buyer/seller addresses.
        """
        async for msg in self._iter_subscription(
            [{"type": "trades", "coin": coin}],
            "trades",
            log_label="Trade WS",
        ):
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
        async for msg in self._iter_subscription(
            [{"type": "trades", "coin": coin} for coin in coins],
            "trades",
            log_label="Trade WS",
        ):
            for trade in parse_ws_trades(msg):
                yield trade

    async def stream_all_mids(
        self,
    ) -> AsyncIterator[dict[str, float]]:
        """Yield mid-price updates for all assets.

        Yields:
            Dict mapping coin name to mid price.
        """
        async for msg in self._iter_subscription(
            [{"type": "allMids"}],
            "allMids",
            log_label="AllMids WS",
        ):
            yield parse_ws_all_mids(msg)

    async def stream_clearinghouse_states(
        self,
        users: list[str],
    ) -> AsyncIterator[tuple[str, list[Position]]]:
        """Yield real-time position updates for tracked whale addresses.

        Opens a single WebSocket connection and subscribes to
        ``clearinghouseState`` for each user. Subscribe frames bypass
        the shared throttle lock — user-position subscribes are pure
        state registrations, and holding the global lock for N × 50
        ms would stall coin subscribes on peer trade connections.

        Args:
            users: List of 0x wallet addresses to subscribe to.

        Yields:
            Tuple of (address, positions) on each push update.
        """
        async for data in self._iter_subscription(
            [{"type": "clearinghouseState", "user": user} for user in users],
            "clearinghouseState",
            log_label="Position WS",
            throttle_subscribes=False,
        ):
            user_addr = data.get("subscription", {}).get("user", "")
            if not user_addr:
                continue
            positions = parse_user_state(data.get("data", {}), user_addr)
            yield user_addr, positions

    async def stream_asset_ctxs(self, coins: list[str]) -> AsyncIterator[AssetSnapshot]:
        """Yield real-time asset context updates for native perpetual coins.

        Subscribes to ``activeAssetCtx`` for each coin on a single WS
        connection, following the ``stream_trades_multi`` multiplexing
        pattern.  HL sends an initial snapshot per coin on subscribe
        (``isSnapshot: true``) — yielded identically to live updates.

        Args:
            coins: Native perpetual asset names to subscribe to.

        Yields:
            AssetSnapshot on each push update (including initial snapshots).
        """
        async for data in self._iter_subscription(
            [{"type": "activeAssetCtx", "coin": coin} for coin in coins],
            "activeAssetCtx",
            log_label="Asset ctx WS",
        ):
            snapshot = parse_ws_active_asset_ctx(data)
            if snapshot is not None:
                yield snapshot

    async def stream_l2_book(self, coin: str) -> AsyncIterator[L2Book]:
        """Yield L2 book updates for a coin.

        Args:
            coin: Asset name.

        Yields:
            Updated L2 book snapshots.
        """
        async for msg in self._iter_subscription(
            [{"type": "l2Book", "coin": coin}],
            "l2Book",
            log_label="L2 WS",
        ):
            data = msg.get("data", {})
            book_data = dict(data)
            book_data.setdefault("coin", coin)
            book_data.setdefault("time", int(time.time() * 1000))
            yield parse_l2_snapshot(book_data)
