"""Long-lived HL ``candle`` channel multiplexer.

Owns a single WebSocket connection to Hyperliquid and reconciles its
active subscriptions against a desired-set published in
:class:`hypersussy.app.state.SharedState`. Each incoming candle is
written back to SharedState via ``push_candle``, where ``/ws/live``
clients pick it up.

This is intentionally separate from :class:`HyperLiquidStream`
because the candle subscription set is dynamic — driven by which
``(coin, interval)`` pairs are currently being viewed in the
dashboard, not by a static coin universe at startup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import orjson
import websockets
from websockets.asyncio.client import ClientConnection

from hypersussy.app.state import SharedState
from hypersussy.exchange.hyperliquid._ws_common import (
    DISCONNECT_ERRORS,
    MAX_RECONNECT_DELAY_S,
    RECONNECT_DELAY_S,
    parse_ws_message,
    ping_loop,
)
from hypersussy.exchange.hyperliquid.parsers import parse_ws_candle
from hypersussy.exchange.hyperliquid.websocket import WsThrottle

logger = logging.getLogger(__name__)

_RECONCILE_INTERVAL_S = 0.5

# HL accepts a fixed set of candle intervals — every other interval
# is rejected with an error response. Source: HL API docs.
VALID_CANDLE_INTERVALS: frozenset[str] = frozenset(
    {
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    }
)


class CandleStreamRegistry:
    """Refcounted manager for HL candle WS subscriptions.

    Reads :meth:`SharedState.get_desired_candle_keys` on a 500 ms
    reconcile cadence and adds/removes HL subscriptions to match.
    Incoming candle messages are dispatched into
    :meth:`SharedState.push_candle`.

    Args:
        ws_url: HL WebSocket endpoint URL.
        state: Shared state instance — read for desired keys, written
            for incoming candles.
        throttle: Optional shared :class:`WsThrottle` for connect/sub
            pacing. A new instance is created if not supplied.
    """

    def __init__(
        self,
        ws_url: str,
        state: SharedState,
        throttle: WsThrottle | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._state = state
        self._throttle = throttle or WsThrottle()
        self._ws: ClientConnection | None = None
        self._subscribed: set[tuple[str, str]] = set()

    async def run(self) -> None:
        """Main loop: connect, reconcile, receive candles, reconnect.

        Runs until cancelled. Each connection attempt is wrapped in a
        try/except so transient network failures back off
        exponentially without killing the task.
        """
        delay = RECONNECT_DELAY_S
        while True:
            try:
                self._ws = await self._connect()
                logger.info("Candle WS connected")
                ping_task = asyncio.create_task(
                    ping_loop(self._ws), name="candle_ws_ping"
                )
                receive_task = asyncio.create_task(
                    self._receive_loop(self._ws), name="candle_ws_recv"
                )
                reconcile_task = asyncio.create_task(
                    self._reconcile_loop(), name="candle_ws_reconcile"
                )
                try:
                    # First task to finish indicates either a
                    # disconnect or an error worth restarting on.
                    done, pending = await asyncio.wait(
                        [receive_task, reconcile_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    # Surface any exception from the completed task.
                    for task in done:
                        exc = task.exception()
                        if exc is not None and not isinstance(
                            exc, asyncio.CancelledError
                        ):
                            raise exc
                finally:
                    ping_task.cancel()
                    if self._ws is not None:
                        await self._ws.close()
                    self._ws = None
                    self._subscribed.clear()
                # Clean exit (disconnect without exception): reset
                # backoff so the next connect is immediate.
                delay = RECONNECT_DELAY_S
            except asyncio.CancelledError:
                if self._ws is not None:
                    await self._ws.close()
                raise
            except DISCONNECT_ERRORS as exc:
                logger.warning(
                    "Candle WS disconnected: %s. Reconnecting in %ds...",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY_S)

    async def _connect(self) -> ClientConnection:
        await self._throttle.wait_connect()
        return await websockets.connect(
            self._ws_url,
            ping_interval=None,
            max_size=10 * 1024 * 1024,
        )

    async def _receive_loop(self, ws: ClientConnection) -> None:
        """Drain incoming messages and dispatch parsed candles to state."""
        async for raw_msg in ws:
            data = parse_ws_message(raw_msg)
            if data is None:
                continue
            channel = data.get("channel")
            if channel in ("pong", "subscriptionResponse"):
                continue
            if channel != "candle":
                continue
            bar = parse_ws_candle(data)
            if bar is not None:
                self._state.push_candle(bar)

    async def _reconcile_loop(self) -> None:
        """Periodically diff actual vs desired subscriptions."""
        while True:
            try:
                await self._reconcile_once()
            except (websockets.ConnectionClosed, OSError):
                # Receive loop will surface the same error and trigger
                # the outer reconnect; just exit this task.
                return
            await asyncio.sleep(_RECONCILE_INTERVAL_S)

    async def _reconcile_once(self) -> None:
        ws = self._ws
        if ws is None:
            return
        desired = self._state.get_desired_candle_keys()
        # Drop any keys with an interval HL doesn't accept rather than
        # repeatedly hitting the server with rejected subscribes.
        desired = {(c, i) for (c, i) in desired if i in VALID_CANDLE_INTERVALS}

        to_unsubscribe = self._subscribed - desired
        to_subscribe = desired - self._subscribed

        for coin, interval in to_unsubscribe:
            await self._send(
                ws,
                "unsubscribe",
                {"type": "candle", "coin": coin, "interval": interval},
            )
            self._subscribed.discard((coin, interval))
            logger.debug("Candle WS unsubscribed %s@%s", coin, interval)

        for coin, interval in to_subscribe:
            await self._send(
                ws,
                "subscribe",
                {"type": "candle", "coin": coin, "interval": interval},
            )
            self._subscribed.add((coin, interval))
            logger.debug("Candle WS subscribed %s@%s", coin, interval)

    async def _send(
        self,
        ws: ClientConnection,
        method: str,
        subscription: dict[str, Any],
    ) -> None:
        await self._throttle.wait_subscribe()
        msg = orjson.dumps({"method": method, "subscription": subscription})
        await ws.send(msg.decode("utf-8"))
