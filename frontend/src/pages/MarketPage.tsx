import { memo, startTransition, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  alertCountsQuery,
  candlesQuery,
  coinsQuery,
  fundingQuery,
  oiQuery,
  topCoinPositionsQuery,
  topHoldersQuery,
  topWhalesQuery,
  tradeFlowQuery,
} from "../api/queries";
import { useWsStore } from "../api/websocket";
import { AlertsByEngineChart } from "../components/charts/AlertsByEngineChart";
import { CandlestickChart, type OverlayLine } from "../components/charts/CandlestickChart";
import { ChartHeader } from "../components/charts/ChartHeader";
import { ChartToolbar } from "../components/charts/ChartToolbar";
import { FundingChart } from "../components/charts/FundingChart";
import { MarkOracleChart } from "../components/charts/MarkOracleChart";
import { OIChart } from "../components/charts/OIChart";
import { TopHoldersChart } from "../components/charts/TopHoldersChart";
import { TradeFlowChart } from "../components/charts/TradeFlowChart";
import { CoinSelector } from "../components/common/CoinSelector";
import { HoursSelector, type Hours } from "../components/common/HoursSelector";
import { type Interval } from "../components/common/IntervalSelector";
import { MetricCard } from "../components/common/MetricCard";
import { EmptyState } from "../components/common/EmptyState";
import { PanelCard } from "../components/common/PanelCard";
import { PanelToggleBar } from "../components/common/PanelToggleBar";
import { PanelWrapper } from "../components/common/PanelWrapper";
import { SeverityFilterBar, type Severity } from "../components/common/SeverityFilterBar";
import { StatusBanner } from "../components/common/StatusBanner";
import { AlertFeed } from "../components/common/AlertFeed";
import { PageHeader } from "../components/layout/PageHeader";
import { MarketSummaryTable } from "../components/market/MarketSummaryTable";
import { TopHoldersTable } from "../components/market/TopHoldersTable";
import { TopTradersTable } from "../components/market/TopTradersTable";
import { formatUSD } from "../utils/format";
import { useIndicator } from "../stores/indicatorStore";
import {
  computeSMA,
  computeEMA,
  computeVWAP,
  SMA_7_COLOR,
  SMA_20_COLOR,
  EMA_50_COLOR,
  VWAP_COLOR,
} from "../utils/indicators";

const ALL = "All";

const HOURS_FOR_INTERVAL: Record<Interval, number> = {
  "1m": 12,
  "5m": 48,
  "15m": 72,
  "1h": 168,
  "4h": 504,
  "1d": 2160,
};

const MARKET_PANELS = [
  { key: "metric-cards", label: "Metrics" },
  { key: "market-table", label: "Table" },
  { key: "candlestick", label: "Candles" },
  { key: "oi-chart", label: "OI" },
  { key: "funding-chart", label: "Funding" },
  { key: "mark-oracle", label: "Mark/Oracle", defaultVisible: false },
  { key: "top-holders", label: "Holders" },
  { key: "trade-flow", label: "Flow" },
  { key: "top-holders-list", label: "Top Holders" },
  { key: "top-traders", label: "Volume" },
  { key: "alert-feed", label: "Alerts" },
  { key: "alerts-engine", label: "By Engine", defaultVisible: false },
];

function parseIntervalParam(value: string | null): Interval {
  if (value && value in HOURS_FOR_INTERVAL) {
    return value as Interval;
  }
  return "1h";
}

// ---------------------------------------------------------------------------
// Sidebar components — each owns its own WS subscription so updates here
// don't cascade into the chart area.
// ---------------------------------------------------------------------------

/** Metric cards sourced from live WS snapshots. */
const MetricSidebar = memo(function MetricSidebar() {
  const snapshots = useWsStore((s) => s.snapshots);
  const liveAlertCount = useWsStore((s) => s.liveAlerts.length);

  const { count, totalOI, totalVol } = useMemo(() => {
    const list = Object.values(snapshots);
    return {
      count: list.length,
      totalOI: list.reduce((s, c) => s + c.open_interest_usd, 0),
      totalVol: list.reduce((s, c) => s + c.day_volume_usd, 0),
    };
  }, [snapshots]);

  const scrollToAlerts = () => {
    document
      .getElementById("alert-feed-anchor")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-1 gap-3">
      <MetricCard label="Assets Tracked" value={String(count)} />
      <MetricCard label="Total OI" value={formatUSD(totalOI)} />
      <MetricCard label="24h Volume" value={formatUSD(totalVol)} />
      <MetricCard
        label="Live Alerts"
        value={String(liveAlertCount)}
        valueClassName={liveAlertCount > 0 ? "text-hs-orange" : undefined}
        onClick={scrollToAlerts}
      />
    </div>
  );
});

/** Live alerts feed + severity filter + alerts-by-engine chart. */
const AlertSidebar = memo(function AlertSidebar() {
  const liveAlerts = useWsStore((s) => s.liveAlerts);
  const [severityFilter, setSeverityFilter] = useState<Severity | null>(null);
  const { data: alertCounts = {} } = useQuery(alertCountsQuery(0));

  const severityCounts = useMemo(
    () => ({
      critical: liveAlerts.filter((a) => a.severity === "critical").length,
      high: liveAlerts.filter((a) => a.severity === "high").length,
      medium: liveAlerts.filter((a) => a.severity === "medium").length,
      low: liveAlerts.filter((a) => a.severity === "low").length,
    }),
    [liveAlerts]
  );

  const displayAlerts = useMemo(
    () =>
      severityFilter
        ? liveAlerts.filter((a) => a.severity === severityFilter)
        : liveAlerts,
    [liveAlerts, severityFilter]
  );

  return (
    <>
      <PanelWrapper panelKey="alert-feed">
        <div id="alert-feed-anchor" className="scroll-mt-4">
          <PanelCard title="Live Alerts">
            <SeverityFilterBar
              counts={severityCounts}
              active={severityFilter}
              onToggle={setSeverityFilter}
            />
            <AlertFeed alerts={displayAlerts} maxRows={20} />
          </PanelCard>
        </div>
      </PanelWrapper>

      <PanelWrapper panelKey="alerts-engine" defaultVisible={false}>
        <PanelCard title="Alerts by Engine">
          <AlertsByEngineChart counts={alertCounts} height={180} />
        </PanelCard>
      </PanelWrapper>
    </>
  );
});

/** Status banner that subscribes to health/connected only. */
const StatusInfo = memo(function StatusInfo() {
  const health = useWsStore((s) => s.health);
  const connected = useWsStore((s) => s.connected);
  return <StatusBanner health={health} connected={connected} />;
});

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function MarketPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const coin = searchParams.get("coin") ?? "";
  const coin2 = searchParams.get("coin2") ?? "";
  const interval = parseIntervalParam(searchParams.get("interval"));
  const [hours, setHours] = useState<Hours>(24);

  const coinMode = coin !== "";

  const handleCoinChange = (c: string) => {
    startTransition(() => {
      const next: Record<string, string> = {};
      if (c && c !== ALL) {
        next.coin = c;
        next.interval = interval;
        // Drop coin2 if it would become a self-compare
        if (coin2 && coin2 !== c) next.coin2 = coin2;
      }
      setSearchParams(next, { replace: true });
    });
  };

  const handleIntervalChange = (iv: Interval) => {
    startTransition(() => {
      const next: Record<string, string> = { coin, interval: iv };
      if (coin2) next.coin2 = coin2;
      setSearchParams(next, { replace: true });
    });
  };

  const handleCoin2Change = (c: string) => {
    startTransition(() => {
      const next: Record<string, string> = { coin, interval };
      if (c && c !== ALL && c !== coin) next.coin2 = c;
      setSearchParams(next, { replace: true });
    });
  };

  const clearCoin2 = () => {
    startTransition(() => {
      setSearchParams({ coin, interval }, { replace: true });
    });
  };

  const candleHours = HOURS_FOR_INTERVAL[interval];

  // --- Data queries (only active in coin mode) ---
  const { data: coins = [] } = useQuery(coinsQuery());

  const { data: candles = [] } = useQuery({
    ...candlesQuery(coin, interval, candleHours),
    enabled: coinMode,
  });
  const { data: oiData = [] } = useQuery({
    ...oiQuery(coin, hours),
    enabled: coinMode,
  });
  const { data: fundingData = [] } = useQuery({
    ...fundingQuery(coin, hours),
    enabled: coinMode,
  });
  const { data: topHolders = [] } = useQuery({
    ...topHoldersQuery(coin, hours, 15),
    enabled: coinMode,
  });
  const { data: topCoinPositions = [] } = useQuery({
    ...topCoinPositionsQuery(coin, 25),
    enabled: coinMode,
  });
  const { data: tradeFlow = [] } = useQuery({
    ...tradeFlowQuery(coin, hours),
    enabled: coinMode,
  });
  const { data: topWhales = [] } = useQuery({
    ...topWhalesQuery(coin, hours),
    enabled: coinMode,
  });

  const compare = coinMode && coin2 !== "" && coin2 !== coin;
  const { data: oiData2 = [] } = useQuery({
    ...oiQuery(coin2, hours),
    enabled: compare,
  });
  const { data: fundingData2 = [] } = useQuery({
    ...fundingQuery(coin2, hours),
    enabled: compare,
  });

  // Indicator toggles
  const showSMA7 = useIndicator("sma7");
  const showSMA20 = useIndicator("sma20", true);
  const showEMA50 = useIndicator("ema50");
  const showVWAP = useIndicator("vwap");
  const showOI = useIndicator("oi");
  const showFunding = useIndicator("funding");

  // OI/funding queries spanning the candle time window (for chart overlays).
  // Only fetched when the corresponding indicator is enabled — on long intervals
  // (e.g. 1d → 2160h) these are large series we shouldn't pull eagerly.
  const { data: oiForChart = [] } = useQuery({
    ...oiQuery(coin, candleHours),
    enabled: coinMode && showOI,
  });
  const { data: fundingForChart = [] } = useQuery({
    ...fundingQuery(coin, candleHours),
    enabled: coinMode && showFunding,
  });

  const chartOverlays = useMemo<OverlayLine[]>(() => {
    const lines: OverlayLine[] = [];
    if (showSMA7) lines.push({ key: "sma7", data: computeSMA(candles, 7), color: SMA_7_COLOR });
    if (showSMA20) lines.push({ key: "sma20", data: computeSMA(candles, 20), color: SMA_20_COLOR });
    if (showEMA50) lines.push({ key: "ema50", data: computeEMA(candles, 50), color: EMA_50_COLOR });
    if (showVWAP) lines.push({ key: "vwap", data: computeVWAP(candles), color: VWAP_COLOR });
    return lines;
  }, [candles, showSMA7, showSMA20, showEMA50, showVWAP]);

  const allCoins = useMemo(
    () => (coins.length > 0 ? [ALL, ...coins] : []),
    [coins]
  );
  const coinSelectorValue = coin || ALL;

  return (
    <div>
      <PageHeader title="Market">
        <StatusInfo />
        <CoinSelector
          coins={allCoins}
          value={coinSelectorValue}
          onChange={handleCoinChange}
        />
        {coinMode && (
          <div className="flex items-center gap-1">
            <select
              value={coin2}
              onChange={(e) => handleCoin2Change(e.target.value)}
              className="rounded-[10px] border border-hs-grid bg-hs-surface px-3 py-1.5 text-sm
                         text-hs-text focus:border-hs-green focus:outline-none"
            >
              <option value="">Compare…</option>
              {coins.filter((c) => c !== coin).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            {coin2 && (
              <button
                onClick={clearCoin2}
                className="text-xs text-hs-grey hover:text-hs-red px-1"
                title="Clear comparison"
              >
                ×
              </button>
            )}
          </div>
        )}
        {coinMode && (
          <HoursSelector
            value={hours}
            onChange={(h) => startTransition(() => setHours(h))}
          />
        )}
        <PanelToggleBar panels={MARKET_PANELS} />
      </PageHeader>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Main column */}
        <div className="flex-1 min-w-0 space-y-4">

          {/* Overview mode: market summary table */}
          {!coinMode && (
            <PanelWrapper panelKey="market-table">
              <div className="bg-hs-surface border border-hs-grid rounded-2xl">
                <div className="border-b border-hs-grid px-4 py-3">
                  <h2 className="text-hs-text font-medium">Market Overview</h2>
                </div>
                <MarketSummaryTable onSelectCoin={handleCoinChange} />
              </div>
            </PanelWrapper>
          )}

          {/* Analytics mode: charts */}
          {coinMode && (
            <>
              <PanelWrapper panelKey="candlestick">
                <div className="bg-black border border-[#1a1a1a] rounded-2xl overflow-hidden">
                  <ChartHeader
                    coin={coin}
                    interval={interval}
                    onIntervalChange={handleIntervalChange}
                  />
                  <ChartToolbar />
                  {candles.length > 0 ? (
                    <CandlestickChart
                      candles={candles}
                      height={460}
                      overlays={chartOverlays}
                      oiData={oiForChart}
                      showOI={showOI}
                      fundingData={fundingForChart}
                      showFundingMarkers={showFunding}
                    />
                  ) : (
                    <p className="text-gray-500 text-sm py-12 text-center">
                      No candle data for {coin} ({interval}).
                    </p>
                  )}
                </div>
              </PanelWrapper>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <PanelWrapper panelKey="oi-chart">
                  <PanelCard
                    title={`Open Interest${compare ? ` — ${coin} vs ${coin2}` : ""} — ${hours}h`}
                  >
                    {oiData.length > 0 ? (
                      <OIChart
                        data={oiData}
                        height={200}
                        label1={coin}
                        data2={compare ? oiData2 : undefined}
                        label2={coin2 || undefined}
                      />
                    ) : (
                      <EmptyState message="No OI data." compact />
                    )}
                  </PanelCard>
                </PanelWrapper>

                <PanelWrapper panelKey="funding-chart">
                  <PanelCard
                    title={`Funding Rate${compare ? ` — ${coin} vs ${coin2}` : ""} — ${hours}h`}
                  >
                    {fundingData.length > 0 ? (
                      <FundingChart
                        data={fundingData}
                        height={200}
                        label1={coin}
                        data2={compare ? fundingData2 : undefined}
                        label2={coin2 || undefined}
                      />
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
                    ) : (
                      <EmptyState message="No data." compact />
                    )}
                  </PanelCard>
                </PanelWrapper>

                <PanelWrapper panelKey="trade-flow">
                  <PanelCard title={`Trade Flow — ${hours}h`}>
                    {tradeFlow.length > 0 ? (
                      <TradeFlowChart data={tradeFlow} />
                    ) : (
                      <EmptyState message="No data." compact />
                    )}
                  </PanelCard>
                </PanelWrapper>
              </div>

              <PanelWrapper panelKey="mark-oracle" defaultVisible={false}>
                <PanelCard title={`Mark vs Oracle — ${hours}h`}>
                  <MarkOracleChart data={fundingData} height={240} />
                </PanelCard>
              </PanelWrapper>

              <PanelWrapper panelKey="top-holders-list">
                <TopHoldersTable
                  coin={coin}
                  positions={topCoinPositions}
                />
              </PanelWrapper>

              <PanelWrapper panelKey="top-traders">
                <TopTradersTable
                  coin={coin}
                  hours={hours}
                  traders={topWhales}
                />
              </PanelWrapper>
            </>
          )}
        </div>

        {/* Side column */}
        <div className="w-full lg:w-72 shrink-0 space-y-4">
          <PanelWrapper panelKey="metric-cards">
            <MetricSidebar />
          </PanelWrapper>

          <AlertSidebar />
        </div>
      </div>
    </div>
  );
}
