"""WebSocket endpoint /ws/live — server-push stream of live market data.

Protocol (server → client JSON messages):
    {"type": "health",    "data": {...}, "timestamp_ms": <int>}
    {"type": "snapshots", "data": {"BTC": {...}, ...}, "timestamp_ms": <int>}
    {"type": "alert",     "data": {...}, "timestamp_ms": <int>}

The loop polls SharedState every 2 seconds and only pushes snapshots when
the underlying data has changed (tracked by last_snapshot_ms).  Alerts are
deduplicated by a high-water-mark on timestamp_ms so each alert is sent
exactly once per connected client.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hypersussy.app.state import LiveSnapshot, SharedState
from hypersussy.models import Alert

router = APIRouter()

_POLL_INTERVAL = 2.0  # seconds between state polls
_SEEN_ALERT_IDS_MAX = 500


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


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    """Push live snapshots, alerts, and health to connected clients.

    Clients receive three message types differentiated by the ``type`` field.
    The connection is kept alive until the client disconnects or the server
    shuts down.

    Args:
        websocket: The active WebSocket connection.
    """
    await websocket.accept()

    state: SharedState = websocket.app.state.shared

    last_snapshot_ms: int = -1
    seen_alert_ids: set[str] = set()
    seen_alert_order: deque[str] = deque()

    try:
        while True:
            now_ms = int(time.time() * 1000)

            # -- health --
            health = state.get_runtime_health()
            await websocket.send_json(
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
                }
            )

            # -- snapshots (only when data changed) --
            if (
                health.last_snapshot_ms is not None
                and health.last_snapshot_ms != last_snapshot_ms
            ):
                snapshots = state.get_snapshots()
                await websocket.send_json(
                    {
                        "type": "snapshots",
                        "data": {
                            coin: _snapshot_to_dict(snap)
                            for coin, snap in snapshots.items()
                        },
                        "timestamp_ms": now_ms,
                    }
                )
                last_snapshot_ms = health.last_snapshot_ms

            # -- new alerts (deduplicated by alert ID per connection) --
            recent_alerts = state.get_recent_alerts(limit=50)
            new_alerts = _select_unsent_alerts(recent_alerts, seen_alert_ids)
            for alert in reversed(new_alerts):  # send oldest-first
                await websocket.send_json(
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
                    }
                )
            if new_alerts:
                _remember_sent_alerts(new_alerts, seen_alert_ids, seen_alert_order)

            await asyncio.sleep(_POLL_INTERVAL)

    except WebSocketDisconnect:
        pass
