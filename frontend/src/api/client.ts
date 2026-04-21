/**
 * Thin fetch wrapper for the HyperSussy REST API.
 *
 * All helpers return typed promises and throw on non-OK HTTP responses.
 * Every request is bounded by ``REQUEST_TIMEOUT_MS`` — without that, a
 * stalled connection would hold a React Query slot open until the
 * browser's own (multi-minute) timeout fires.
 */

import type {
  AlertItem,
  AlertSummaryItem,
  CandleItem,
  CoinPositionItem,
  ConfigFieldItem,
  ConfigResponse,
  FillPageResponse,
  FundingSnapshotItem,
  HealthResponse,
  OISnapshotItem,
  PositionItem,
  RealizedPnlResponse,
  StorageStatsResponse,
  TopHolderItem,
  TopWhaleItem,
  TradeFlowItem,
  TrackedAddressItem,
  WalletAccountResponse,
} from "./types";

const BASE = "/api";
const REQUEST_TIMEOUT_MS = 30_000;

async function request(path: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${BASE}${path}`, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function assertOk(res: Response): Promise<Response> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res;
}

function buildQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) qs.set(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function get<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  const res = await assertOk(await request(path + buildQuery(params)));
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await assertOk(
    await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
  return res.json() as Promise<T>;
}

async function del<T = void>(path: string): Promise<T> {
  const res = await assertOk(await request(path, { method: "DELETE" }));
  // 204 No Content has no body; everything else is parsed as JSON.
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await assertOk(
    await request(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
  return res.json() as Promise<T>;
}

// -- Health --

export const fetchHealth = (): Promise<HealthResponse> => get("/health");

// ``/health/logs`` returns ``text/plain``, so we can't route it
// through ``get<T>`` (JSON-parsing). Share the timeout + assertOk
// pipeline instead of re-implementing another fetch site.
export async function fetchLogs(lines = 500): Promise<string> {
  const res = await assertOk(await request(`/health/logs${buildQuery({ lines })}`));
  return res.text();
}

// -- Snapshots --

export const fetchCoins = (): Promise<string[]> => get("/snapshots/coins");

export const fetchOI = (coin: string, hours = 24): Promise<OISnapshotItem[]> =>
  get(`/snapshots/oi/${encodeURIComponent(coin)}`, { hours });

export const fetchFunding = (
  coin: string,
  hours = 24
): Promise<FundingSnapshotItem[]> =>
  get(`/snapshots/funding/${encodeURIComponent(coin)}`, { hours });

export const fetchLatestOI = (): Promise<Record<string, number>> =>
  get("/snapshots/latest-oi");

// -- Alerts --

export const fetchAlerts = (
  limit = 200,
  since_ms = 0
): Promise<AlertItem[]> => get("/alerts", { limit, since_ms });

export const fetchAlertCounts = (
  since_ms = 0
): Promise<Record<string, number>> => get("/alerts/counts", { since_ms });

export const fetchAlertsByAddress = (
  address: string,
  limit = 20
): Promise<AlertSummaryItem[]> =>
  get(`/alerts/by-address/${encodeURIComponent(address)}`, { limit });

// -- Trades --

export const fetchTopWhales = (
  coin: string,
  hours = 1
): Promise<TopWhaleItem[]> =>
  get(`/trades/top-whales/${encodeURIComponent(coin)}`, { hours });

export const fetchTopHolders = (
  coin: string,
  hours = 24,
  limit = 15
): Promise<TopHolderItem[]> =>
  get(`/trades/top-holders/${encodeURIComponent(coin)}`, { hours, limit });

export const fetchTradeFlow = (
  coin: string,
  hours = 24
): Promise<TradeFlowItem[]> =>
  get(`/trades/flow/${encodeURIComponent(coin)}`, { hours });

// -- Candles --

export const fetchCandles = (
  coin: string,
  interval = "1h",
  hours = 48
): Promise<CandleItem[]> =>
  get(`/candles/${encodeURIComponent(coin)}`, { interval, hours });

// -- Whales --

export const fetchWhales = (limit = 50): Promise<TrackedAddressItem[]> =>
  get("/whales", { limit });

export const fetchWhaleCount = (): Promise<{ count: number }> =>
  get("/whales/count");

export const fetchWhalePositions = (address: string): Promise<PositionItem[]> =>
  get(`/whales/positions/${encodeURIComponent(address)}`);

export const fetchTopCoinPositions = (
  coin: string,
  limit = 25
): Promise<CoinPositionItem[]> =>
  get(`/whales/top/${encodeURIComponent(coin)}`, { limit });

export const addWhale = (
  address: string,
  label: string
): Promise<{ address: string }> => post("/whales", { address, label });

export const removeWhale = (address: string): Promise<void> =>
  del<void>(`/whales/${encodeURIComponent(address)}`);

export const fetchRealizedPnl = (
  address: string,
): Promise<RealizedPnlResponse> =>
  get(`/whales/pnl/${encodeURIComponent(address)}`);

export const fetchWalletAccount = (address: string): Promise<WalletAccountResponse> =>
  get(`/whales/account/${encodeURIComponent(address)}`);

// -- Stats --

export const fetchStorageStats = (): Promise<StorageStatsResponse> =>
  get("/stats/storage");

// -- Config --

export const fetchConfig = (): Promise<ConfigResponse> => get("/config");

export const updateConfigField = (
  key: string,
  value: number | boolean,
): Promise<ConfigFieldItem> =>
  put(`/config/${encodeURIComponent(key)}`, { value });

export const resetConfigField = (key: string): Promise<ConfigFieldItem> =>
  del<ConfigFieldItem>(`/config/${encodeURIComponent(key)}`);

export const fetchFills = (
  address: string,
  beforeMs?: number,
  limit = 50,
): Promise<FillPageResponse> =>
  get(`/whales/fills/${encodeURIComponent(address)}`, {
    limit,
    before_ms: beforeMs,
  });
