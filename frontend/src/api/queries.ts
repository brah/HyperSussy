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
    staleTime: 5_000,
    refetchInterval: 5_000,
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

export const latestOIQuery = () =>
  queryOptions({
    queryKey: ["latest-oi"],
    queryFn: api.fetchLatestOI,
    staleTime: 10_000,
    refetchInterval: 10_000,
  });

export const alertsQuery = (limit: number, since_ms: number) =>
  queryOptions({
    queryKey: ["alerts", limit, since_ms],
    queryFn: () => api.fetchAlerts(limit, since_ms),
    staleTime: 5_000,
    refetchInterval: 5_000,
  });

export const alertCountsQuery = (since_ms: number) =>
  queryOptions({
    queryKey: ["alert-counts", since_ms],
    queryFn: () => api.fetchAlertCounts(since_ms),
    staleTime: 5_000,
    refetchInterval: 5_000,
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

export const candlesQuery = (coin: string, interval: string, hours: number) =>
  queryOptions({
    queryKey: ["candles", coin, interval, hours],
    queryFn: () => api.fetchCandles(coin, interval, hours),
    staleTime: 30_000,
    enabled: coin.length > 0,
    placeholderData: keepPreviousData,
  });

export const whalesQuery = (limit: number) =>
  queryOptions({
    queryKey: ["whales", limit],
    queryFn: () => api.fetchWhales(limit),
    staleTime: 5_000,
    refetchInterval: 5_000,
  });

export const whaleCountQuery = () =>
  queryOptions({
    queryKey: ["whale-count"],
    queryFn: api.fetchWhaleCount,
    staleTime: 5_000,
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

export const topCoinPositionsQuery = (coin: string, limit: number) =>
  queryOptions({
    queryKey: ["top-coin-positions", coin, limit],
    queryFn: () => api.fetchTopCoinPositions(coin, limit),
    staleTime: 10_000,
    refetchInterval: 10_000,
    enabled: coin.length > 0,
  });
