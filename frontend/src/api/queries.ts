/**
 * React Query query-key constants and query-function factories.
 *
 * Stale times are calibrated to query frequency:
 *   - health / live data: 5 s
 *   - snapshots: 10 s
 *   - candles: 30 s
 *   - static lists (coins, whales): 30 s
 */

import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";
import * as api from "./client";

export const healthQuery = () =>
  queryOptions({
    queryKey: ["health"],
    queryFn: api.fetchHealth,
    // Health is pushed via the WS `health` channel on the same cadence
    // the orchestrator emits — see api/websocket.ts. The REST poll only
    // runs once on mount as a hydration fallback before the WS connects.
    staleTime: 5_000,
  });

export const coinsQuery = () =>
  queryOptions({
    queryKey: ["coins"],
    queryFn: api.fetchCoins,
    staleTime: 30_000,
  });

export const oiQuery = (coin: string, hours: number) =>
  queryOptions({
    queryKey: ["oi", coin, hours],
    queryFn: () => api.fetchOI(coin, hours),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

export const fundingQuery = (coin: string, hours: number) =>
  queryOptions({
    queryKey: ["funding", coin, hours],
    queryFn: () => api.fetchFunding(coin, hours),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

// Latest OI: the REST endpoint is used only as a hydration fallback.
// Live OI values flow in on every ``snapshots`` WS push, which the
// charts subscribe to directly. A refetchInterval here would produce
// redundant HTTP traffic for data the WS is already delivering.
export const latestOIQuery = () =>
  queryOptions({
    queryKey: ["latest-oi"],
    queryFn: api.fetchLatestOI,
    staleTime: 10_000,
  });

// Alerts: the WS /ws/live channel delivers each new alert as it is
// dispatched. This REST query is the initial-load fallback so the
// feed isn't empty before the WS connects (and a safety net when the
// WS is down). No refetchInterval for the same reason as latestOI.
export const alertsQuery = (limit: number, since_ms: number) =>
  queryOptions({
    queryKey: ["alerts", limit, since_ms],
    queryFn: () => api.fetchAlerts(limit, since_ms),
    staleTime: 5_000,
  });

// Alert counts: aggregate per alert_type. The WS alert channel emits
// individual alerts, not running totals, so we can't rebuild this
// from WS state without re-computing from the full alert history.
// The consumer (Alerts-by-Engine sub-panel) is already off by
// default; when visible, a 30 s refresh is plenty for a "counts
// since midnight" style summary without hammering the API.
export const alertCountsQuery = (since_ms: number) =>
  queryOptions({
    queryKey: ["alert-counts", since_ms],
    queryFn: () => api.fetchAlertCounts(since_ms),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

export const alertsByAddressQuery = (address: string, limit: number) =>
  queryOptions({
    queryKey: ["alerts-by-address", address, limit],
    queryFn: () => api.fetchAlertsByAddress(address, limit),
    staleTime: 5_000,
    enabled: address.length === 42,
  });

export const topWhalesQuery = (coin: string, hours: number) =>
  queryOptions({
    queryKey: ["top-whales", coin, hours],
    queryFn: () => api.fetchTopWhales(coin, hours),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

export const topHoldersQuery = (coin: string, hours: number, limit: number) =>
  queryOptions({
    queryKey: ["top-holders", coin, hours, limit],
    queryFn: () => api.fetchTopHolders(coin, hours, limit),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

export const tradeFlowQuery = (coin: string, hours: number) =>
  queryOptions({
    queryKey: ["trade-flow", coin, hours],
    queryFn: () => api.fetchTradeFlow(coin, hours),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

/**
 * Cursor-paginated candle history.
 *
 * Page 0 is the newest ``CANDLE_PAGE_SIZE`` bars; each subsequent
 * page is fetched on demand via ``fetchNextPage()`` when the user
 * scrolls close to the left edge of the chart. ``initialPageParam``
 * is ``undefined`` so the first fetch sends no ``before_ms``, which
 * the backend treats as "newest bars" with an implicit top-up.
 *
 * ``getNextPageParam`` returns the oldest timestamp of the page
 * just received — or ``undefined`` when the server returned fewer
 * than the page size, which is our signal that history is
 * exhausted.
 */
export const CANDLE_PAGE_SIZE = 1500;

export const candlesInfiniteQuery = (coin: string, interval: string) =>
  infiniteQueryOptions({
    queryKey: ["candles", coin, interval],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      api.fetchCandles(coin, interval, {
        before_ms: pageParam,
        limit: CANDLE_PAGE_SIZE,
      }),
    getNextPageParam: (lastPage) => {
      if (lastPage.length < CANDLE_PAGE_SIZE) return undefined;
      return lastPage[0]?.timestamp_ms;
    },
    staleTime: 30_000,
    enabled: coin.length > 0,
  });

// Tracked whales change once per user action (manual add/remove via the
// wallets page) plus rare background discovery promotions. 60 s is the
// right cadence — the previous 5 s polling produced 12 redundant
// requests per minute against an effectively static dataset.
export const whalesQuery = (limit: number) =>
  queryOptions({
    queryKey: ["whales", limit],
    queryFn: () => api.fetchWhales(limit),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const whaleCountQuery = () =>
  queryOptions({
    queryKey: ["whale-count"],
    queryFn: api.fetchWhaleCount,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const whalePositionsQuery = (address: string) =>
  queryOptions({
    queryKey: ["whale-positions", address],
    queryFn: () => api.fetchWhalePositions(address),
    staleTime: 10_000,
    enabled: address.length === 42,
  });

export const fillsInfiniteQuery = (address: string) =>
  infiniteQueryOptions({
    queryKey: ["fills", address],
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      api.fetchFills(address, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 60_000,
    enabled: address.length === 42,
  });

export const realizedPnlQuery = (address: string) =>
  queryOptions({
    queryKey: ["realized-pnl", address],
    queryFn: () => api.fetchRealizedPnl(address),
    staleTime: 60_000,
    enabled: address.length === 42,
  });

export const configQuery = () =>
  queryOptions({
    queryKey: ["config"],
    queryFn: api.fetchConfig,
    staleTime: 30_000,
  });

export const storageStatsQuery = () =>
  queryOptions({
    queryKey: ["storage-stats"],
    queryFn: api.fetchStorageStats,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

export const walletAccountQuery = (address: string) =>
  queryOptions({
    queryKey: ["wallet-account", address],
    queryFn: () => api.fetchWalletAccount(address),
    staleTime: 60_000,
    enabled: address.length === 42,
  });

export const topCoinPositionsQuery = (coin: string, limit: number) =>
  queryOptions({
    queryKey: ["top-coin-positions", coin, limit],
    queryFn: () => api.fetchTopCoinPositions(coin, limit),
    staleTime: 10_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });
