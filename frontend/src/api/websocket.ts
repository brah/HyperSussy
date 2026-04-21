/**
 * WebSocket client and Zustand live-state store.
 *
 * Connects to /ws/live and dispatches server messages into a Zustand store
 * that components subscribe to via selectors. Reconnects with exponential
 * backoff (1 s -> 2 s -> 4 s -> ... capped at 30 s) on disconnection.
 */

import { create } from "zustand";
import type {
  AlertItem,
  CandleItem,
  HealthResponse,
  LiveSnapshot,
  WsMessage,
} from "./types";

const MAX_LIVE_ALERTS = 100;
const BACKOFF_CAP_MS = 30_000;
const STOP_GRACE_MS = 100;
// After this many consecutive reconnect failures we flip ``unreachable``
// in the store so the UI can surface a persistent banner. The reconnect
// loop keeps running so a later success clears the flag — the cap is
// purely about user-visible state, not about giving up.
const UNREACHABLE_AFTER_FAILURES = 8;

/** Composite key for `lastCandles` lookups. */
export function candleKey(coin: string, interval: string): string {
  return `${coin}:${interval}`;
}

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
  /**
   * True when reconnection has failed enough times in a row that
   * we've stopped quietly retrying and want the UI to surface a
   * persistent "connection lost" banner. Cleared on the next
   * successful connect.
   */
  unreachable: boolean;
  /**
   * Latest candle per ``coin:interval`` key, populated by the
   * server's ``candle`` channel. Components subscribe via a narrow
   * selector keyed on the active coin/interval to avoid re-renders
   * when an unrelated chart receives an update.
   */
  lastCandles: Record<string, CandleItem>;
  setSnapshots: (s: Record<string, LiveSnapshot>) => void;
  addAlert: (a: AlertItem) => void;
  setHealth: (h: HealthResponse) => void;
  setConnected: (c: boolean) => void;
  setUnreachable: (u: boolean) => void;
  setCandle: (coin: string, interval: string, candle: CandleItem) => void;
  removeCandle: (coin: string, interval: string) => void;
}

export const useWsStore = create<WsState>((set) => ({
  snapshots: {},
  liveAlerts: [],
  health: null,
  connected: false,
  unreachable: false,
  lastCandles: {},
  setSnapshots: (snapshots) => set({ snapshots }),
  addAlert: (alert) =>
    set((s) => ({
      // Drop the oldest first so the resulting array is exactly
      // ``MAX_LIVE_ALERTS`` — the previous shape built an N+1 array
      // then sliced to N, allocating twice on every push.
      liveAlerts: [alert, ...s.liveAlerts.slice(0, MAX_LIVE_ALERTS - 1)],
    })),
  setHealth: (health) => set({ health }),
  setConnected: (connected) => set({ connected }),
  setUnreachable: (unreachable) => set({ unreachable }),
  setCandle: (coin, interval, candle) =>
    set((s) => ({
      lastCandles: { ...s.lastCandles, [candleKey(coin, interval)]: candle },
    })),
  // Evict the cached bar for a no-longer-watched (coin, interval) so
  // long sessions browsing many symbols don't accrete stale entries.
  // Called from watchCandles/unwatchCandles; the store is the sole
  // owner of lastCandles so there's no race with readers.
  removeCandle: (coin, interval) =>
    set((s) => {
      const key = candleKey(coin, interval);
      if (!(key in s.lastCandles)) return s;
      const next = { ...s.lastCandles };
      delete next[key];
      return { lastCandles: next };
    }),
}));

let _ws: WebSocket | null = null;
let _backoffMs = 1_000;
let _subscriberCount = 0;
let _allowReconnect = true;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _stopTimer: ReturnType<typeof setTimeout> | null = null;
// Consecutive failed reconnect attempts since the last successful open.
// Feeds the ``unreachable`` flag once it crosses the threshold.
let _failureCount = 0;
// The candle subscription the dashboard *wants* the backend to be on.
// Re-sent after every reconnect so a transient drop doesn't leave the
// active chart silently disconnected from its candle stream.
let _desiredCandleWatch: { coin: string; interval: string } | null = null;

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
    // A successful open clears the unreachable banner and resets
    // the failure counter. A reconnect that opens but closes
    // seconds later will bump the counter again below.
    _failureCount = 0;
    useWsStore.getState().setUnreachable(false);
    _backoffMs = 1_000;
    // Re-send the desired candle watch on every (re)connect so a
    // transient disconnect doesn't strand the active chart.
    flushDesiredCandleWatch();
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
      case "candle":
        // Drop trailing candle messages for a key we no longer want.
        // Without this guard, a bar that arrives after unwatchCandles
        // (but before the backend processes it) would re-insert the
        // entry we just evicted in removeCandle.
        if (
          _desiredCandleWatch !== null &&
          _desiredCandleWatch.coin === msg.data.coin &&
          _desiredCandleWatch.interval === msg.data.interval
        ) {
          useWsStore
            .getState()
            .setCandle(msg.data.coin, msg.data.interval, msg.data.candle);
        }
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

    _failureCount += 1;
    if (_failureCount >= UNREACHABLE_AFTER_FAILURES) {
      useWsStore.getState().setUnreachable(true);
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

function flushDesiredCandleWatch(): void {
  if (_ws === null || _ws.readyState !== WebSocket.OPEN) return;
  if (_desiredCandleWatch === null) {
    _ws.send(JSON.stringify({ type: "unwatch_candles" }));
    return;
  }
  _ws.send(
    JSON.stringify({
      type: "watch_candles",
      coin: _desiredCandleWatch.coin,
      interval: _desiredCandleWatch.interval,
    }),
  );
}

/**
 * Tell the backend we want live candle updates for ``(coin, interval)``.
 *
 * Holds at most one watch at a time per WebSocket connection — calling
 * this with a different key automatically releases the previous one
 * server-side. Safe to call before the WS is open: the request is
 * stashed and sent on the next ``onopen`` (including reconnects).
 */
export function watchCandles(coin: string, interval: string): void {
  if (
    _desiredCandleWatch?.coin === coin &&
    _desiredCandleWatch?.interval === interval
  ) {
    return;
  }
  const previous = _desiredCandleWatch;
  _desiredCandleWatch = { coin, interval };
  if (previous !== null) {
    useWsStore.getState().removeCandle(previous.coin, previous.interval);
  }
  flushDesiredCandleWatch();
}

/** Drop the active candle subscription, if any. */
export function unwatchCandles(): void {
  if (_desiredCandleWatch === null) return;
  const previous = _desiredCandleWatch;
  _desiredCandleWatch = null;
  useWsStore.getState().removeCandle(previous.coin, previous.interval);
  flushDesiredCandleWatch();
}
