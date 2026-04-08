/**
 * Thin fetch wrapper for the HyperSussy REST API.
 *
 * All helpers return typed promises and throw on non-OK HTTP responses.
 */

import type {
  AlertItem,
  AlertSummaryItem,
  CandleItem,
  CoinPositionItem,
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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
}

// -- Health --

export const fetchHealth = (): Promise<HealthResponse> => get("/health");

export async function fetchLogs(lines = 500): Promise<string> {
  const res = await fetch(`/api/health/logs?lines=${lines}`);
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return text;
}

// -- Snapshots --

export const fetchCoins = (): Promise<string[]> => get("/snapshots/coins");

export const fetchOI = (coin: string, hours = 24): Promise<OISnapshotItem[]> =>
  get(`/snapshots/oi/${encodeURIComponent(coin)}?hours=${hours}`);

export const fetchFunding = (
  coin: string,
  hours = 24
): Promise<FundingSnapshotItem[]> =>
  get(`/snapshots/funding/${encodeURIComponent(coin)}?hours=${hours}`);

export const fetchLatestOI = (): Promise<Record<string, number>> =>
  get("/snapshots/latest-oi");

// -- Alerts --

export const fetchAlerts = (
  limit = 200,
  since_ms = 0
): Promise<AlertItem[]> =>
  get(`/alerts?limit=${limit}&since_ms=${since_ms}`);

export const fetchAlertCounts = (
  since_ms = 0
): Promise<Record<string, number>> =>
  get(`/alerts/counts?since_ms=${since_ms}`);

export const fetchAlertsByAddress = (
  address: string,
  limit = 20
): Promise<AlertSummaryItem[]> =>
  get(`/alerts/by-address/${encodeURIComponent(address)}?limit=${limit}`);

// -- Trades --

export const fetchTopWhales = (
  coin: string,
  hours = 1
): Promise<TopWhaleItem[]> =>
  get(`/trades/top-whales/${encodeURIComponent(coin)}?hours=${hours}`);

export const fetchTopHolders = (
  coin: string,
  hours = 24,
  limit = 15
): Promise<TopHolderItem[]> =>
  get(
    `/trades/top-holders/${encodeURIComponent(coin)}?hours=${hours}&limit=${limit}`
  );

export const fetchTradeFlow = (
  coin: string,
  hours = 24
): Promise<TradeFlowItem[]> =>
  get(`/trades/flow/${encodeURIComponent(coin)}?hours=${hours}`);

// -- Candles --

export const fetchCandles = (
  coin: string,
  interval = "1h",
  hours = 48
): Promise<CandleItem[]> =>
  get(
    `/candles/${encodeURIComponent(coin)}?interval=${encodeURIComponent(interval)}&hours=${hours}`
  );

// -- Whales --

export const fetchWhales = (limit = 50): Promise<TrackedAddressItem[]> =>
  get(`/whales?limit=${limit}`);

export const fetchWhaleCount = (): Promise<{ count: number }> =>
  get("/whales/count");

export const fetchWhalePositions = (address: string): Promise<PositionItem[]> =>
  get(`/whales/positions/${encodeURIComponent(address)}`);

export const fetchTopCoinPositions = (
  coin: string,
  limit = 25
): Promise<CoinPositionItem[]> =>
  get(`/whales/top/${encodeURIComponent(coin)}?limit=${limit}`);

export const addWhale = (
  address: string,
  label: string
): Promise<{ address: string }> => post("/whales", { address, label });

export const removeWhale = (address: string): Promise<void> =>
  del(`/whales/${encodeURIComponent(address)}`);

export const fetchRealizedPnl = (
  address: string,
): Promise<RealizedPnlResponse> =>
  get(`/whales/pnl/${encodeURIComponent(address)}`);

export const fetchWalletAccount = (address: string): Promise<WalletAccountResponse> =>
  get(`/whales/account/${encodeURIComponent(address)}`);

// -- Stats --

export const fetchStorageStats = (): Promise<StorageStatsResponse> =>
  get("/stats/storage");

export const fetchFills = (
  address: string,
  beforeMs?: number,
  limit = 50,
): Promise<FillPageResponse> => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (beforeMs != null) params.set("before_ms", String(beforeMs));
  return get(`/whales/fills/${encodeURIComponent(address)}?${params}`);
};
