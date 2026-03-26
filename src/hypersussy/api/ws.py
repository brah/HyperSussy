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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hypersussy.app.state import LiveSnapshot, SharedState

router = APIRouter()

_POLL_INTERVAL = 2.0  # seconds between state polls


def _snapshot_to_dict(snap: LiveSnapshot) -> dict[str, object]:
    return dataclasses.asdict(snap)


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
    last_alert_ms: int = -1

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

            # -- new alerts (high-water mark by timestamp) --
            recent_alerts = state.get_recent_alerts(limit=50)
            new_alerts = [
                a for a in recent_alerts if a.timestamp_ms > last_alert_ms
            ]
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
                last_alert_ms = new_alerts[0].timestamp_ms

            await asyncio.sleep(_POLL_INTERVAL)

    except WebSocketDisconnect:
        pass
