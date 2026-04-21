"""Shared primitives for Hyperliquid WebSocket clients.

Both :mod:`hypersussy.exchange.hyperliquid.websocket` and
:mod:`hypersussy.exchange.hyperliquid.candle_stream` own their own
WS connections but share the same protocol-level concerns:

* HL expects application-level ``{"method": "ping"}`` messages
  rather than WebSocket protocol pings.
* Reconnect with exponential backoff, capped.
* JSON framing via ``orjson``.
* The set of disconnection-style exceptions that drive the
  reconnect loop.

Hoisting these to a shared module means the two clients can't
drift — an earlier version had three separate copies of the ping
interval constant and two slightly different JSON parse helpers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import orjson
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

# Matches the HL SDK. 50 s is comfortably under HL's 60 s idle
# disconnect so the server never sees an idle connection.
PING_INTERVAL_S = 50
# Initial and capped reconnect delays (seconds). The caller doubles
# the delay after each failed attempt until the cap.
RECONNECT_DELAY_S = 2
MAX_RECONNECT_DELAY_S = 60

# Exceptions that indicate the connection is gone / unusable and the
# caller should reconnect. ``websockets.ConnectionClosed`` covers
# both normal and abnormal closures; ``InvalidURI`` is included
# because it surfaces here when the URL is templated from settings
# and the caller wants a retry rather than a crash; ``OSError``
# covers DNS failures and connection refused.
DISCONNECT_ERRORS: tuple[type[BaseException], ...] = (
    websockets.ConnectionClosed,
    websockets.InvalidURI,
    OSError,
)


async def ping_loop(ws: ClientConnection) -> None:
    """Send application-level pings until the connection closes or is cancelled.

    HL expects ``{"method": "ping"}`` JSON messages rather than
    protocol-level pings, so the ``websockets`` library's own
    ``ping_interval`` must be disabled when the connection is
    opened (see callers).
    """
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            await ws.send('{"method":"ping"}')
    except (websockets.ConnectionClosed, asyncio.CancelledError):
        pass


def parse_ws_message(raw_msg: str | bytes) -> dict[str, Any] | None:
    """Parse an incoming WebSocket frame as JSON.

    ``orjson.loads`` accepts ``bytes``, ``bytearray``, ``memoryview``,
    and ``str`` directly — so the old "encode str→bytes then parse"
    round-trip some callers used was dead weight and has been
    removed. Non-JSON frames (e.g. HL's "Websocket connection
    established." greeting) return ``None``.

    Args:
        raw_msg: Raw frame from the WebSocket.

    Returns:
        The parsed object if it's a JSON dict, else ``None``.
    """
    try:
        result = orjson.loads(raw_msg)
    except orjson.JSONDecodeError:
        preview = raw_msg[:120] if isinstance(raw_msg, str) else raw_msg[:120]
        logger.debug("Non-JSON WS message: %r", preview)
        return None
    if isinstance(result, dict):
        return result
    return None
