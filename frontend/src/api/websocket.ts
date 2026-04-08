/**
 * WebSocket client and Zustand live-state store.
 *
 * Connects to /ws/live and dispatches server messages into a Zustand store
 * that components subscribe to via selectors. Reconnects with exponential
 * backoff (1 s -> 2 s -> 4 s -> ... capped at 30 s) on disconnection.
 */

import { create } from "zustand";
import type { AlertItem, HealthResponse, LiveSnapshot, WsMessage } from "./types";

const MAX_LIVE_ALERTS = 100;
const BACKOFF_CAP_MS = 30_000;
const STOP_GRACE_MS = 100;

// Snapshot updates from the backend can arrive several times per second.
// Each WS message replaces the entire snapshots dict with a fresh top-level
// reference, which would re-render every component subscribing to it (the
// market summary table, metric sidebar, top-holders, etc.) on every push.
// Throttle commits to the React store with a leading-edge + trailing flush
// pattern: the first push goes through immediately, then subsequent pushes
// during the window are coalesced into a single commit at the trailing edge.
const SNAPSHOT_FLUSH_MS = 500;
let _pendingSnapshots: Record<string, LiveSnapshot> | null = null;
let _snapshotFlushTimer: ReturnType<typeof setTimeout> | null = null;

function flushPendingSnapshots(): void {
  _snapshotFlushTimer = null;
  if (_pendingSnapshots !== null) {
    useWsStore.getState().setSnapshots(_pendingSnapshots);
    _pendingSnapshots = null;
  }
}

function commitSnapshotsThrottled(snapshots: Record<string, LiveSnapshot>): void {
  if (_snapshotFlushTimer === null) {
    // Leading edge — commit immediately so the first message is never delayed.
    useWsStore.getState().setSnapshots(snapshots);
    _snapshotFlushTimer = setTimeout(flushPendingSnapshots, SNAPSHOT_FLUSH_MS);
  } else {
    // Trailing edge — coalesce into the timer; only the most recent payload
    // matters because each push is a full snapshot of all coins.
    _pendingSnapshots = snapshots;
  }
}

function clearSnapshotFlushTimer(): void {
  if (_snapshotFlushTimer !== null) {
    clearTimeout(_snapshotFlushTimer);
    _snapshotFlushTimer = null;
  }
  _pendingSnapshots = null;
}

interface WsState {
  snapshots: Record<string, LiveSnapshot>;
  liveAlerts: AlertItem[];
  health: HealthResponse | null;
  connected: boolean;
  setSnapshots: (s: Record<string, LiveSnapshot>) => void;
  addAlert: (a: AlertItem) => void;
  setHealth: (h: HealthResponse) => void;
  setConnected: (c: boolean) => void;
}

export const useWsStore = create<WsState>((set) => ({
  snapshots: {},
  liveAlerts: [],
  health: null,
  connected: false,
  setSnapshots: (snapshots) => set({ snapshots }),
  addAlert: (alert) =>
    set((s) => ({
      liveAlerts: [alert, ...s.liveAlerts].slice(0, MAX_LIVE_ALERTS),
    })),
  setHealth: (health) => set({ health }),
  setConnected: (connected) => set({ connected }),
}));

let _ws: WebSocket | null = null;
let _backoffMs = 1_000;
let _subscriberCount = 0;
let _allowReconnect = true;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _stopTimer: ReturnType<typeof setTimeout> | null = null;

function clearReconnectTimer(): void {
  if (_reconnectTimer !== null) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
}

function clearStopTimer(): void {
  if (_stopTimer !== null) {
    clearTimeout(_stopTimer);
    _stopTimer = null;
  }
}

function scheduleReconnect(): void {
  clearReconnectTimer();
  _reconnectTimer = setTimeout(() => {
    _backoffMs = Math.min(_backoffMs * 2, BACKOFF_CAP_MS);
    if (_subscriberCount > 0) {
      connect();
    }
  }, _backoffMs);
}

function connect(): void {
  if (_subscriberCount === 0) {
    return;
  }

  const { setConnected, addAlert, setHealth } = useWsStore.getState();

  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const url = import.meta.env.DEV
    ? "ws://localhost:8000/ws/live"
    : `${scheme}://${location.host}/ws/live`;

  _allowReconnect = true;
  _ws = new WebSocket(url);

  _ws.onopen = () => {
    setConnected(true);
    _backoffMs = 1_000;
  };

  _ws.onmessage = (ev: MessageEvent<string>) => {
    let msg: WsMessage;
    try {
      msg = JSON.parse(ev.data) as WsMessage;
    } catch (err) {
      // Production: silently drop the bad frame so a single corrupt
      // payload from the backend cannot break the live feed. Dev:
      // surface the error so we actually find the bug. Truncate the
      // payload preview to keep the console readable.
      if (import.meta.env.DEV) {
        const preview = ev.data.length > 200 ? ev.data.slice(0, 200) + "…" : ev.data;
        console.warn("[ws] failed to parse message:", err, preview);
      }
      return;
    }

    switch (msg.type) {
      case "snapshots":
        commitSnapshotsThrottled(msg.data);
        break;
      case "alert":
        addAlert(msg.data);
        break;
      case "health":
        setHealth(msg.data);
        break;
    }
  };

  _ws.onclose = () => {
    setConnected(false);
    _ws = null;

    // Drop any in-flight throttle state. Without this a trailing flush
    // scheduled before the disconnect would still fire and commit stale
    // data after the socket is gone, and the first message from the
    // reconnected socket would be coalesced into the lingering timer
    // instead of taking the leading-edge fast path.
    clearSnapshotFlushTimer();

    if (!_allowReconnect || _subscriberCount === 0) {
      _allowReconnect = true;
      return;
    }

    scheduleReconnect();
  };

  _ws.onerror = () => {
    // onclose fires automatically after onerror; closing here would race against
    // a CONNECTING socket and produce a "closed before established" warning.
  };
}

export function startWebSocket(): void {
  _subscriberCount += 1;
  clearStopTimer();
  clearReconnectTimer();

  if (_ws !== null) {
    return;
  }

  connect();
}

export function stopWebSocket(): void {
  _subscriberCount = Math.max(0, _subscriberCount - 1);
  if (_subscriberCount > 0) {
    return;
  }

  clearReconnectTimer();
  clearStopTimer();

  // React Strict Mode intentionally mounts, unmounts, and remounts once in
  // development. Delaying teardown avoids closing a still-connecting socket
  // during that probe cycle while still cleaning up on a real app unmount.
  _stopTimer = setTimeout(() => {
    _stopTimer = null;
    if (_subscriberCount > 0) {
      return;
    }

    _allowReconnect = false;
    clearSnapshotFlushTimer();
    useWsStore.getState().setConnected(false);
    _ws?.close();
    _ws = null;
  }, STOP_GRACE_MS);
}
