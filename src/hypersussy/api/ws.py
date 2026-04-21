"""WebSocket endpoint /ws/live — bidirectional live market data stream.

Server → client JSON messages:
    {"type": "health",    "data": {...}, "timestamp_ms": <int>}
    {"type": "snapshots", "data": {"BTC": {...}, ...}, "timestamp_ms": <int>}
    {"type": "alert",     "data": {...}, "timestamp_ms": <int>}
    {"type": "candle",    "data": {"coin": "BTC", "interval": "1m",
                                    "candle": {...}}, "timestamp_ms": <int>}

Client → server JSON messages:
    {"type": "watch_candles",   "coin": "BTC", "interval": "1m"}
    {"type": "unwatch_candles"}

The send loop polls SharedState every 2 seconds for snapshots / alerts /
health and every 100 ms for candle deltas (cheap; only fires when the
watched key's seq counter has advanced). Alerts are deduplicated by ID
so each alert is sent exactly once per connected client.

Each connection holds at most one active candle watch. The receive
task acquires/releases the corresponding refcount in SharedState; the
``CandleStreamRegistry`` background task handles the actual HL WS
subscribe/unsubscribe.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hypersussy.app.state import (
    CandleEntry,
    LiveSnapshot,
    RuntimeHealth,
    SharedState,
)
from hypersussy.models import Alert

logger = logging.getLogger(__name__)

router = APIRouter()

# Snapshot/alert/health are pushed on a 2 s cadence; the candle path
# polls the seq counter on a 250 ms tick — fast enough that a fresh
# bar reaches the client within a single human-perceivable frame
# while halving the per-second push rate compared to a 100 ms tick.
# 4 Hz is indistinguishable from 10 Hz on a 1-minute candle and the
# downstream React render cost scales linearly with this cadence.
_SEND_TICK_S = 0.25
_FULL_PUSH_INTERVAL_S = 2.0
_SEEN_ALERT_IDS_MAX = 500
# A ``send_json`` call stalls when the client's outbound buffer is
# full (slow network, a browser tab throttled in the background).
# Giving each send a hard deadline lets the server close a wedged
# connection instead of letting one slow client hold the send loop
# hostage while candle seq counters pile up behind it.
_SEND_TIMEOUT_S = 5.0


def _snapshot_to_dict(snap: LiveSnapshot) -> dict[str, object]:
    return dataclasses.asdict(snap)


def _select_unsent_alerts(
    recent_alerts: list[Alert],
    seen_alert_ids: set[str],
) -> list[Alert]:
    """Return alerts whose IDs have not yet been sent on this connection."""
    return [alert for alert in recent_alerts if alert.alert_id not in seen_alert_ids]


def _remember_sent_alerts(
    alerts: list[Alert],
    seen_alert_ids: set[str],
    seen_alert_order: deque[str],
) -> None:
    """Record sent alert IDs while keeping the de-dup window bounded."""
    for alert in alerts:
        if alert.alert_id in seen_alert_ids:
            continue
        seen_alert_ids.add(alert.alert_id)
        seen_alert_order.append(alert.alert_id)
    while len(seen_alert_order) > _SEEN_ALERT_IDS_MAX:
        seen_alert_ids.discard(seen_alert_order.popleft())


async def _send_with_timeout(websocket: WebSocket, payload: dict[str, object]) -> None:
    """Send a JSON frame with a bounded deadline.

    A timeout raises :class:`TimeoutError`, which the outer task
    reaper treats the same as a disconnect — the send and receive
    tasks both unwind and the connection is torn down. Without
    this, a single slow client pushing back on TCP flow control
    would stall every future send on this connection indefinitely.
    """
    await asyncio.wait_for(websocket.send_json(payload), timeout=_SEND_TIMEOUT_S)


def _candle_payload(entry: CandleEntry) -> dict[str, object]:
    """Serialise a CandleEntry's bar into the wire format."""
    bar = entry.bar
    return {
        "coin": bar.coin,
        "interval": bar.interval,
        "candle": {
            "timestamp_ms": bar.timestamp_ms,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "num_trades": bar.num_trades,
        },
    }


class _CandleWatch:
    """Per-connection candle subscription holder.

    Holds at most one active ``(coin, interval)`` reservation against
    SharedState's refcounted desired-keys map. Switching keys
    releases the previous reservation atomically before acquiring
    the next one.
    """

    __slots__ = ("_state", "current", "last_seq")

    def __init__(self, state: SharedState) -> None:
        self._state = state
        self.current: tuple[str, str] | None = None
        self.last_seq: int = -1

    def watch(self, coin: str, interval: str) -> None:
        new_key = (coin, interval)
        if self.current == new_key:
            return
        if self.current is not None:
            self._state.release_candle_subscription(*self.current)
        self._state.acquire_candle_subscription(coin, interval)
        self.current = new_key
        self.last_seq = -1

    def clear(self) -> None:
        if self.current is not None:
            self._state.release_candle_subscription(*self.current)
            self.current = None
            self.last_seq = -1


async def _receive_loop(
    websocket: WebSocket,
    watch: _CandleWatch,
) -> None:
    """Drain client → server messages and apply watch_candles requests."""
    while True:
        raw = await websocket.receive_text()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("ws_live: ignoring non-JSON client message")
            continue
        msg_type = msg.get("type") if isinstance(msg, dict) else None
        if msg_type == "watch_candles":
            coin = msg.get("coin")
            interval = msg.get("interval")
            if (
                isinstance(coin, str)
                and isinstance(interval, str)
                and coin
                and interval
            ):
                watch.watch(coin, interval)
        elif msg_type == "unwatch_candles":
            watch.clear()


async def _send_loop(
    websocket: WebSocket,
    state: SharedState,
    watch: _CandleWatch,
) -> None:
    """Push snapshots/alerts/health on the slow tick + candles on the fast tick."""
    last_snapshot_ms: int = -1
    last_health_signature: tuple[object, ...] | None = None
    seen_alert_ids: set[str] = set()
    seen_alert_order: deque[str] = deque()
    last_full_push = 0.0

    while True:
        now_mono = time.monotonic()
        now_ms = int(time.time() * 1000)

        if now_mono - last_full_push >= _FULL_PUSH_INTERVAL_S:
            last_health_signature = await _push_full(
                websocket,
                state,
                now_ms,
                last_snapshot_ms,
                last_health_signature,
                seen_alert_ids,
                seen_alert_order,
            )
            # Refresh last_snapshot_ms from state for the next tick.
            health = state.get_runtime_health()
            if health.last_snapshot_ms is not None:
                last_snapshot_ms = health.last_snapshot_ms
            last_full_push = now_mono

        # -- candle (fast tick) --
        if watch.current is not None:
            entry = state.get_candle_entry(*watch.current)
            if entry is not None and entry.seq != watch.last_seq:
                await _send_with_timeout(
                    websocket,
                    {
                        "type": "candle",
                        "data": _candle_payload(entry),
                        "timestamp_ms": now_ms,
                    },
                )
                watch.last_seq = entry.seq

        await asyncio.sleep(_SEND_TICK_S)


async def _push_full(
    websocket: WebSocket,
    state: SharedState,
    now_ms: int,
    last_snapshot_ms: int,
    last_health_signature: tuple[object, ...] | None,
    seen_alert_ids: set[str],
    seen_alert_order: deque[str],
) -> tuple[object, ...]:
    """One slow-cadence push: health + snapshots-if-changed + new alerts.

    Returns the health signature used this tick so the caller can
    skip the next push if nothing has changed. Each of 100 connected
    clients receiving the same unchanged health frame twice a second
    is pure waste — comparing a small tuple is cheap and lets us
    drop the frame entirely.
    """
    health = state.get_runtime_health()
    signature = _health_signature(health)
    if signature != last_health_signature:
        await _send_with_timeout(
            websocket,
            {
                "type": "health",
                "data": {
                    "is_running": health.is_running,
                    "snapshot_count": health.snapshot_count,
                    "last_snapshot_ms": health.last_snapshot_ms,
                    "last_alert_ms": health.last_alert_ms,
                    "engine_errors": [
                        {
                            "source": e.source,
                            "message": e.message,
                            "timestamp_ms": e.timestamp_ms,
                        }
                        for e in health.engine_errors
                    ],
                    "runtime_errors": [
                        {
                            "source": e.source,
                            "message": e.message,
                            "timestamp_ms": e.timestamp_ms,
                        }
                        for e in health.runtime_errors
                    ],
                },
                "timestamp_ms": now_ms,
            },
        )

    if (
        health.last_snapshot_ms is not None
        and health.last_snapshot_ms != last_snapshot_ms
    ):
        snapshots = state.get_snapshots()
        await _send_with_timeout(
            websocket,
            {
                "type": "snapshots",
                "data": {
                    coin: _snapshot_to_dict(snap) for coin, snap in snapshots.items()
                },
                "timestamp_ms": now_ms,
            },
        )

    recent_alerts = state.get_recent_alerts(limit=50)
    new_alerts = _select_unsent_alerts(recent_alerts, seen_alert_ids)
    for alert in reversed(new_alerts):  # oldest-first
        await _send_with_timeout(
            websocket,
            {
                "type": "alert",
                "data": {
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "coin": alert.coin,
                    "title": alert.title,
                    "description": alert.description,
                    "timestamp_ms": alert.timestamp_ms,
                    "exchange": alert.exchange,
                    "address": alert.metadata.get("address"),
                },
                "timestamp_ms": now_ms,
            },
        )
    if new_alerts:
        _remember_sent_alerts(new_alerts, seen_alert_ids, seen_alert_order)
    return signature


def _health_signature(health: RuntimeHealth) -> tuple[object, ...]:
    """Compact tuple capturing everything the health payload exposes.

    Two calls returning equal tuples means the serialised health
    frame would be byte-identical, so the outer loop can drop the
    push entirely.
    """
    return (
        health.is_running,
        health.snapshot_count,
        health.last_snapshot_ms,
        health.last_alert_ms,
        tuple((e.source, e.message, e.timestamp_ms) for e in health.engine_errors),
        tuple((e.source, e.message, e.timestamp_ms) for e in health.runtime_errors),
    )


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    """Bidirectional live feed: snapshots, alerts, health, and candles.

    Server-push messages on the slow tick (every 2 s) cover snapshots,
    alerts, and health. The candle stream is opt-in: clients send a
    ``watch_candles`` upstream message to declare interest in a
    specific ``(coin, interval)`` pair, after which candle pushes
    arrive on the fast tick (every 100 ms).

    Args:
        websocket: The active WebSocket connection.
    """
    await websocket.accept()

    state: SharedState = websocket.app.state.shared
    watch = _CandleWatch(state)

    receive_task = asyncio.create_task(
        _receive_loop(websocket, watch), name="ws_live_recv"
    )
    send_task = asyncio.create_task(
        _send_loop(websocket, state, watch), name="ws_live_send"
    )

    try:
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        # Surface any exception that wasn't a clean disconnect.
        # ``TimeoutError`` here means ``_send_with_timeout`` gave up
        # on a wedged client — treated as a disconnect, logged at
        # INFO rather than WARNING because it's a client health
        # signal, not a server bug.
        for task in done:
            exc = task.exception()
            if exc is None:
                continue
            if isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                continue
            if isinstance(exc, TimeoutError):
                logger.info("ws_live send stalled past %.1fs; closing", _SEND_TIMEOUT_S)
                continue
            logger.warning("ws_live task ended with %s", exc)
    finally:
        watch.clear()
