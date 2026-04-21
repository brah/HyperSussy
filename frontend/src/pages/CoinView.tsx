/**
 * Coin analytics view — lazy-loaded by MarketPage so that recharts and
 * lightweight-charts are NOT included in the initial bundle.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQueries, useQuery } from "@tanstack/react-query";
import {
  candlesInfiniteQuery,
  fundingQuery,
  oiQuery,
  topCoinPositionsQuery,
  topHoldersQuery,
  topWhalesQuery,
  tradeFlowQuery,
} from "../api/queries";
import { unwatchCandles, watchCandles } from "../api/websocket";
import { CandlestickChart } from "../components/charts/CandlestickChart";
import { ChartHeader } from "../components/charts/ChartHeader";
import { ChartToolbar } from "../components/charts/ChartToolbar";
import { FundingChart } from "../components/charts/FundingChart";
import { MarkOracleChart } from "../components/charts/MarkOracleChart";
import { OIChart, type OIMode } from "../components/charts/OIChart";
import { TopHoldersChart } from "../components/charts/TopHoldersChart";
import { TradeFlowChart } from "../components/charts/TradeFlowChart";
import { EmptyState } from "../components/common/EmptyState";
import { PanelCard } from "../components/common/PanelCard";
import { PanelWrapper } from "../components/common/PanelWrapper";
import { TopHoldersTable } from "../components/market/TopHoldersTable";
import { TopTradersTable } from "../components/market/TopTradersTable";
import { useIndicator } from "../stores/indicatorStore";
import { usePanelVisible } from "../stores/panelStore";
import type { Hours } from "../components/common/HoursSelector";
import { type Interval } from "../components/common/IntervalSelector";

// Maximum number of compare coins supported (keeps hooks unconditional).
const MAX_COMPARE = 4;

const HOURS_FOR_INTERVAL: Record<Interval, number> = {
  "1m": 12,
  "5m": 48,
  "15m": 72,
  "1h": 168,
  "4h": 504,
  "1d": 2160,
};

interface CoinViewProps {
  coin: string;
  /** Up to MAX_COMPARE additional coins for comparison. */
  coin2s: string[];
  interval: Interval;
  hours: Hours;
  onIntervalChange: (iv: Interval) => void;
}

export default function CoinView({ coin, coin2s, interval, hours, onIntervalChange }: Readonly<CoinViewProps>) {
  const [oiMode, setOiMode] = useState<OIMode>("pct");
  // OI / Funding indicator overlays still use a time-windowed REST
  // query because they're not paginated — sized to the interval via
  // HOURS_FOR_INTERVAL. The main candle series has moved to
  // useInfiniteQuery so deep history loads on pan-to-left without
  // growing this initial payload.
  const candleHours = HOURS_FOR_INTERVAL[interval];
  // Clamp to MAX_COMPARE and filter out the primary coin.
  // Memoized so downstream useMemos can list it as a stable dependency.
  const compareCoins = useMemo(
    () => coin2s.filter((c) => c !== coin).slice(0, MAX_COMPARE),
    [coin2s, coin],
  );
  const comparing = compareCoins.length > 0;

  // Panel visibility — gates the matching queries so toggling a panel
  // off via PanelToggleBar also stops its background fetches. The keys
  // mirror the entries in MarketPage.MARKET_PANELS.
  const showCandlestick = usePanelVisible("candlestick", true);
  const showFundingPanel = usePanelVisible("funding-chart", true);
  const showTopHolders = usePanelVisible("top-holders", true);
  const showTradeFlow = usePanelVisible("trade-flow", true);
  const showTopHoldersList = usePanelVisible("top-holders-list", true);
  const showTopTraders = usePanelVisible("top-traders", true);
  const showMarkOracle = usePanelVisible("mark-oracle", false);

  // OI/funding sub-pane toggles — read here so we can gate the
  // matching React Query fetches. The SMA/EMA/VWAP indicator toggles
  // live entirely inside CandlestickChart, which keeps CoinView from
  // re-rendering on every WS candle push.
  const showOI = useIndicator("oi", true);
  const showFunding = useIndicator("funding");

  // Primary coin data — every query gates on its containing panel so
  // hidden panels don't issue background fetches. The four chart
  // panels that render an empty-state branch on `data.length === 0`
  // also pull `isLoading` so the first toggle-on of a hidden panel
  // shows a "Loading…" placeholder instead of flashing "No data".
  // `isCandlesPlaceholder` flags the keepPreviousData window during a
  // coin transition — forwarded into CandlestickChart so its overlay
  // math skips live-patching while the candles array still belongs
  // to the previous coin.
  const {
    data: candlesData,
    isLoading: candlesLoading,
    isPlaceholderData: isCandlesPlaceholder,
    hasNextPage: hasOlderCandles,
    isFetchingNextPage: isFetchingOlderCandles,
    fetchNextPage: fetchOlderCandles,
  } = useInfiniteQuery({
    ...candlesInfiniteQuery(coin, interval),
    enabled: showCandlestick && coin.length > 0,
  });

  // Flatten the infinite-query pages into one oldest-first array.
  // React Query stores pages in request order (newest page first in
  // ``pages[0]``, older pages appended as the user scrolls left), and
  // each page is itself oldest-first within its window. Flattening
  // [older_page, ..., newest_page] → concatenated oldest-first array
  // feeds lightweight-charts' ``setData`` cleanly without a sort.
  const candles = useMemo(() => {
    if (!candlesData) return [];
    const merged = [];
    for (let i = candlesData.pages.length - 1; i >= 0; i--) {
      merged.push(...candlesData.pages[i]);
    }
    return merged;
  }, [candlesData]);

  // Chart asks for older bars by calling this; we translate into a
  // React Query ``fetchNextPage`` and swallow the result promise —
  // the useInfiniteQuery state updates drive the re-render.
  const onLoadOlderCandles = useCallback(() => {
    if (!hasOlderCandles || isFetchingOlderCandles) return;
    void fetchOlderCandles();
  }, [hasOlderCandles, isFetchingOlderCandles, fetchOlderCandles]);
  // Plain `oiData` (using `hours`) is only consumed by the OI compare
  // panel, which renders only when `comparing`. The candle sub-pane
  // uses `oiForChart` (different hours window).
  const { data: oiData = [] } = useQuery({
    ...oiQuery(coin, hours),
    enabled: comparing && coin.length > 0,
  });
  // `fundingData` feeds the funding-chart panel AND the mark-oracle
  // panel. Either being visible is enough to fetch.
  const { data: fundingData = [], isLoading: fundingLoading } = useQuery({
    ...fundingQuery(coin, hours),
    enabled: (showFundingPanel || showMarkOracle) && coin.length > 0,
  });
  const { data: topHolders = [], isLoading: topHoldersLoading } = useQuery({
    ...topHoldersQuery(coin, hours, 15),
    enabled: showTopHolders && coin.length > 0,
  });
  const { data: topCoinPositions = [] } = useQuery({
    ...topCoinPositionsQuery(coin, 25),
    enabled: showTopHoldersList && coin.length > 0,
  });
  const { data: tradeFlow = [], isLoading: tradeFlowLoading } = useQuery({
    ...tradeFlowQuery(coin, hours),
    enabled: showTradeFlow && coin.length > 0,
  });
  const { data: topWhales = [] } = useQuery({
    ...topWhalesQuery(coin, hours),
    enabled: showTopTraders && coin.length > 0,
  });

  // OI/funding spanning the candle window — only fetched when both
  // the candlestick panel is visible AND the user has the indicator
  // toggled on inside the chart toolbar.
  const { data: oiForChart = [] } = useQuery({
    ...oiQuery(coin, candleHours),
    enabled: showCandlestick && showOI && coin.length > 0,
  });
  const { data: fundingForChart = [] } = useQuery({
    ...fundingQuery(coin, candleHours),
    enabled: showCandlestick && showFunding && coin.length > 0,
  });

  // Compare-coin queries — collapsed from 8 manually-unrolled useQuery
  // calls to two useQueries() arrays keyed by `compareCoins`. The
  // hooks-rules constraint is satisfied by useQueries: it accepts a
  // dynamic-length array. Each pair only fires when the matching
  // panel is visible (OI panel only renders in compare mode; funding
  // panel may still be on without compare).
  const compareOiResults = useQueries({
    queries: compareCoins.map((c) => ({
      ...oiQuery(c, hours),
      enabled: comparing,
    })),
  });
  const compareFundingResults = useQueries({
    queries: compareCoins.map((c) => ({
      ...fundingQuery(c, hours),
      enabled: comparing && showFundingPanel,
    })),
  });

  const compareOI = useMemo(
    () =>
      compareOiResults.map((r, i) => ({
        data: r.data ?? [],
        label: compareCoins[i],
      })),
    [compareOiResults, compareCoins],
  );

  const compareFunding = useMemo(
    () =>
      compareFundingResults.map((r, i) => ({
        data: r.data ?? [],
        label: compareCoins[i],
      })),
    [compareFundingResults, compareCoins],
  );

  // Live candle stream — opt the WS into the active (coin, interval)
  // pair so the candlestick chart can patch the open bar in real time
  // via lightweight-charts' incremental update API. The watch is also
  // gated on the candlestick panel being visible: no point streaming
  // candles for a hidden chart.
  useEffect(() => {
    if (!showCandlestick || coin.length === 0) {
      unwatchCandles();
      return;
    }
    watchCandles(coin, interval);
    return () => {
      unwatchCandles();
    };
  }, [coin, interval, showCandlestick]);

  return (
    <>
      <PanelWrapper panelKey="candlestick">
        <div className="bg-hs-chart-bg border border-hs-chart-border rounded-2xl overflow-hidden">
          <ChartHeader coin={coin} interval={interval} onIntervalChange={onIntervalChange} />
          <ChartToolbar />
          {candles.length > 0 ? (
            <CandlestickChart
              coin={coin}
              interval={interval}
              candles={candles}
              isPlaceholderData={isCandlesPlaceholder}
              height={460}
              oiData={oiForChart}
              showOI={showOI}
              fundingData={fundingForChart}
              showFunding={showFunding}
              onLoadOlder={onLoadOlderCandles}
              hasMoreOlder={hasOlderCandles}
              isLoadingOlder={isFetchingOlderCandles}
            />
          ) : candlesLoading ? (
            <p className="text-gray-500 text-sm py-12 text-center animate-pulse">
              Loading candles…
            </p>
          ) : (
            <p className="text-gray-500 text-sm py-12 text-center">
              No candle data for {coin}.
            </p>
          )}
        </div>
      </PanelWrapper>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* OI panel — only in compare mode; single-coin OI lives in the candle sub-pane */}
        {comparing && (
          <PanelCard
            title={`Open Interest — ${coin} vs ${compareCoins.join(", ")} — ${hours}h`}
            action={
              <div className="flex items-center gap-0.5">
                {(["pct", "usd"] as OIMode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setOiMode(m)}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                      oiMode === m
                        ? "bg-hs-grid text-hs-text"
                        : "text-hs-grey hover:text-hs-text"
                    }`}
                  >
                    {m === "pct" ? "% chg" : "USD"}
                  </button>
                ))}
              </div>
            }
          >
            <OIChart
              series={[{ data: oiData, label: coin }, ...compareOI]}
              mode={oiMode}
              height={200}
            />
          </PanelCard>
        )}

        <PanelWrapper panelKey="funding-chart">
          <PanelCard
            title={"Funding Rate" + (comparing ? ` — ${coin} vs ${compareCoins.join(", ")}` : "") + ` — ${hours}h`}
          >
            {fundingData.length > 0 ? (
              <FundingChart
                data={fundingData}
                label={coin}
                compares={comparing ? compareFunding : undefined}
                height={200}
              />
            ) : fundingLoading ? (
              <EmptyState message="Loading funding…" state="loading" compact />
            ) : (
              <EmptyState message="No funding data." compact />
            )}
          </PanelCard>
        </PanelWrapper>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PanelWrapper panelKey="top-holders">
          <PanelCard title={`Top Holder Concentration — ${hours}h`}>
            {topHolders.length > 0 ? (
              <TopHoldersChart data={topHolders} />
            ) : topHoldersLoading ? (
              <EmptyState message="Loading holders…" state="loading" compact />
            ) : (
              <EmptyState message="No data." compact />
            )}
          </PanelCard>
        </PanelWrapper>

        <PanelWrapper panelKey="trade-flow">
          <PanelCard title={`Trade Flow — ${hours}h`}>
            {tradeFlow.length > 0 ? (
              <TradeFlowChart data={tradeFlow} />
            ) : tradeFlowLoading ? (
              <EmptyState message="Loading flow…" state="loading" compact />
            ) : (
              <EmptyState message="No data." compact />
            )}
          </PanelCard>
        </PanelWrapper>
      </div>

      <PanelWrapper panelKey="mark-oracle" defaultVisible={false}>
        <PanelCard title={`Mark vs Oracle — ${hours}h`}>
          {fundingData.length > 0 ? (
            <MarkOracleChart data={fundingData} height={240} />
          ) : fundingLoading ? (
            <EmptyState message="Loading mark/oracle…" state="loading" compact />
          ) : (
            <EmptyState message="No mark/oracle data." compact />
          )}
        </PanelCard>
      </PanelWrapper>

      <PanelWrapper panelKey="top-holders-list">
        <TopHoldersTable coin={coin} positions={topCoinPositions} />
      </PanelWrapper>

      <PanelWrapper panelKey="top-traders">
        <TopTradersTable coin={coin} hours={hours} traders={topWhales} />
      </PanelWrapper>
    </>
  );
}
