import { lazy, memo, startTransition, Suspense, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import {
  alertCountsQuery,
  coinsQuery,
} from "../api/queries";
import { useWsStore } from "../api/websocket";
const AlertsByEngineChart = lazy(() =>
  import("../components/charts/AlertsByEngineChart").then((m) => ({
    default: m.AlertsByEngineChart,
  })),
);
import { CoinSelector } from "../components/common/CoinSelector";
import { HoursSelector, type Hours } from "../components/common/HoursSelector";
import { MetricCard } from "../components/common/MetricCard";
import { PanelCard } from "../components/common/PanelCard";
import { PanelToggleBar } from "../components/common/PanelToggleBar";
import { PanelWrapper } from "../components/common/PanelWrapper";
import { usePanelVisible } from "../stores/panelStore";
import { SeverityFilterBar, type Severity } from "../components/common/SeverityFilterBar";
import { StatusBanner } from "../components/common/StatusBanner";
import { AlertFeed } from "../components/common/AlertFeed";
import { PageHeader } from "../components/layout/PageHeader";
import { MarketSummaryTable } from "../components/market/MarketSummaryTable";
import { formatUSD } from "../utils/format";

// CoinView contains recharts + lightweight-charts — lazy-load so they are
// excluded from the initial bundle and only fetched when a coin is selected.
const CoinView = lazy(() => import("./CoinView"));

const ALL = "All";

const MARKET_PANELS = [
  { key: "metric-cards", label: "Metrics" },
  { key: "market-table", label: "Table" },
  { key: "candlestick", label: "Candles" },
  { key: "funding-chart", label: "Funding" },
  { key: "mark-oracle", label: "Mark/Oracle", defaultVisible: false },
  { key: "top-holders", label: "Holders" },
  { key: "trade-flow", label: "Flow" },
  { key: "top-holders-list", label: "Top Holders" },
  { key: "top-traders", label: "Volume" },
  { key: "alert-feed", label: "Alerts" },
  { key: "alerts-engine", label: "By Engine", defaultVisible: false },
];

// ---------------------------------------------------------------------------
// Sidebar components — each owns its own WS subscription so updates here
// don't cascade into the chart area.
// ---------------------------------------------------------------------------

/** Metric cards sourced from live WS snapshots. */
const MetricSidebar = memo(function MetricSidebar() {
  // Aggregate inside the Zustand selector with shallow equality so the
  // component skips React renders entirely when the totals haven't changed.
  // Subscribing to `s.snapshots` directly would re-render on every WS push
  // because each push replaces the dict reference.
  const { count, totalOI, totalVol } = useWsStore(
    useShallow((s) => {
      const list = Object.values(s.snapshots);
      return {
        count: list.length,
        totalOI: list.reduce((acc, c) => acc + c.open_interest_usd, 0),
        totalVol: list.reduce((acc, c) => acc + c.day_volume_usd, 0),
      };
    }),
  );
  const liveAlertCount = useWsStore((s) => s.liveAlerts.length);

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
  // Only poll alert counts when the "Alerts by Engine" sub-panel is visible.
  // It defaults to off, so this saves one persistent 5s background fetch.
  const alertsByEngineVisible = usePanelVisible("alerts-engine", false);
  const { data: alertCounts = {} } = useQuery({
    ...alertCountsQuery(0),
    enabled: alertsByEngineVisible,
  });

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
          <Suspense fallback={null}>
            <AlertsByEngineChart counts={alertCounts} height={180} />
          </Suspense>
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

function parseIntervalParam(value: string | null) {
  const valid = { "1m": 1, "5m": 1, "15m": 1, "1h": 1, "4h": 1, "1d": 1 } as const;
  if (value && value in valid) return value as keyof typeof valid;
  return "1h" as const;
}

export function MarketPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const coin = searchParams.get("coin") ?? "";
  const coin2s = useMemo(
    () => (searchParams.get("coin2") ?? "").split(",").filter((c) => c.length > 0),
    [searchParams],
  );
  const interval = parseIntervalParam(searchParams.get("interval"));
  const [hours, setHours] = useState<Hours>(24);

  const coinMode = coin !== "";

  const setParams = (next: Record<string, string>) =>
    setSearchParams(next, { replace: true });

  const handleCoinChange = (c: string) => {
    startTransition(() => {
      const next: Record<string, string> = {};
      if (c && c !== ALL) {
        next.coin = c;
        next.interval = interval;
        const kept = coin2s.filter((x) => x !== c);
        if (kept.length > 0) next.coin2 = kept.join(",");
      }
      setHours(24);
      setParams(next);
    });
  };

  const handleIntervalChange = (iv: string) => {
    startTransition(() => {
      const next: Record<string, string> = { coin, interval: iv };
      if (coin2s.length > 0) next.coin2 = coin2s.join(",");
      setParams(next);
    });
  };

  const handleAddCompare = (c: string) => {
    startTransition(() => {
      if (!c || c === coin || coin2s.includes(c) || coin2s.length >= 4) return;
      const next: Record<string, string> = { coin, interval };
      next.coin2 = [...coin2s, c].join(",");
      setParams(next);
    });
  };

  const handleRemoveCompare = (c: string) => {
    startTransition(() => {
      const kept = coin2s.filter((x) => x !== c);
      const next: Record<string, string> = { coin, interval };
      if (kept.length > 0) next.coin2 = kept.join(",");
      setParams(next);
    });
  };

  const { data: coins = [] } = useQuery(coinsQuery());

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
          <div className="flex flex-wrap items-center gap-1">
            {coin2s.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1 rounded-full border border-hs-grid
                           bg-hs-surface px-2 py-0.5 text-xs text-hs-text"
              >
                {c}
                <button
                  onClick={() => handleRemoveCompare(c)}
                  className="text-hs-grey hover:text-hs-red leading-none"
                  aria-label={`Remove ${c}`}
                >
                  ×
                </button>
              </span>
            ))}
            {coin2s.length < 4 && (
              <select
                value=""
                onChange={(e) => { if (e.target.value) handleAddCompare(e.target.value); }}
                className="rounded-[10px] border border-hs-grid bg-hs-surface px-3 py-1.5 text-sm
                           text-hs-text focus:border-hs-green focus:outline-none"
              >
                <option value="">+ Compare</option>
                {coins.filter((c) => c !== coin && !coin2s.includes(c)).map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
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

          {/* Analytics mode: coin charts — lazy-loaded chunk */}
          {coinMode && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-24 text-hs-grey text-sm">
                  Loading charts…
                </div>
              }
            >
              <CoinView
                coin={coin}
                coin2s={coin2s}
                interval={interval}
                hours={hours}
                onIntervalChange={handleIntervalChange}
              />
            </Suspense>
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
