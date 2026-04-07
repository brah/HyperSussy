/**
 * Coin analytics view — lazy-loaded by MarketPage so that recharts and
 * lightweight-charts are NOT included in the initial bundle.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  candlesQuery,
  fundingQuery,
  oiQuery,
  topCoinPositionsQuery,
  topHoldersQuery,
  topWhalesQuery,
  tradeFlowQuery,
} from "../api/queries";
import { CandlestickChart, type OverlayLine } from "../components/charts/CandlestickChart";
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
import {
  computeSMA,
  computeEMA,
  computeVWAP,
  SMA_7_COLOR,
  SMA_20_COLOR,
  EMA_50_COLOR,
  VWAP_COLOR,
} from "../utils/indicators";
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
  const candleHours = HOURS_FOR_INTERVAL[interval];
  // Clamp to MAX_COMPARE and filter out the primary coin.
  // Memoized so downstream useMemos can list it as a stable dependency.
  const compareCoins = useMemo(
    () => coin2s.filter((c) => c !== coin).slice(0, MAX_COMPARE),
    [coin2s, coin],
  );
  const comparing = compareCoins.length > 0;

  // Primary coin data
  const { data: candles = [] } = useQuery(candlesQuery(coin, interval, candleHours));
  const { data: oiData = [] } = useQuery(oiQuery(coin, hours));
  const { data: fundingData = [] } = useQuery(fundingQuery(coin, hours));
  const { data: topHolders = [] } = useQuery(topHoldersQuery(coin, hours, 15));
  const { data: topCoinPositions = [] } = useQuery(topCoinPositionsQuery(coin, 25));
  const { data: tradeFlow = [] } = useQuery(tradeFlowQuery(coin, hours));
  const { data: topWhales = [] } = useQuery(topWhalesQuery(coin, hours));

  // Indicator toggles
  const showSMA7 = useIndicator("sma7");
  const showSMA20 = useIndicator("sma20", true);
  const showEMA50 = useIndicator("ema50");
  const showVWAP = useIndicator("vwap");
  const showOI = useIndicator("oi", true);
  const showFunding = useIndicator("funding");

  // OI/funding spanning the candle window — only fetched when indicator is on
  const { data: oiForChart = [] } = useQuery({ ...oiQuery(coin, candleHours), enabled: showOI });
  const { data: fundingForChart = [] } = useQuery({ ...fundingQuery(coin, candleHours), enabled: showFunding });

  // Compare coin queries — unconditional slots, enabled by position.
  const { data: oi0 = [] } = useQuery({ ...oiQuery(compareCoins[0] ?? "", hours), enabled: compareCoins.length > 0 });
  const { data: oi1 = [] } = useQuery({ ...oiQuery(compareCoins[1] ?? "", hours), enabled: compareCoins.length > 1 });
  const { data: oi2 = [] } = useQuery({ ...oiQuery(compareCoins[2] ?? "", hours), enabled: compareCoins.length > 2 });
  const { data: oi3 = [] } = useQuery({ ...oiQuery(compareCoins[3] ?? "", hours), enabled: compareCoins.length > 3 });

  const { data: fund0 = [] } = useQuery({ ...fundingQuery(compareCoins[0] ?? "", hours), enabled: compareCoins.length > 0 });
  const { data: fund1 = [] } = useQuery({ ...fundingQuery(compareCoins[1] ?? "", hours), enabled: compareCoins.length > 1 });
  const { data: fund2 = [] } = useQuery({ ...fundingQuery(compareCoins[2] ?? "", hours), enabled: compareCoins.length > 2 });
  const { data: fund3 = [] } = useQuery({ ...fundingQuery(compareCoins[3] ?? "", hours), enabled: compareCoins.length > 3 });

  const compareOI = useMemo(
    () =>
      [oi0, oi1, oi2, oi3]
        .slice(0, compareCoins.length)
        .map((data, i) => ({ data, label: compareCoins[i] })),
    [oi0, oi1, oi2, oi3, compareCoins],
  );

  const compareFunding = useMemo(
    () =>
      [fund0, fund1, fund2, fund3]
        .slice(0, compareCoins.length)
        .map((data, i) => ({ data, label: compareCoins[i] })),
    [fund0, fund1, fund2, fund3, compareCoins],
  );

  const chartOverlays = useMemo<OverlayLine[]>(() => {
    const lines: OverlayLine[] = [];
    if (showSMA7) lines.push({ key: "sma7", data: computeSMA(candles, 7), color: SMA_7_COLOR });
    if (showSMA20) lines.push({ key: "sma20", data: computeSMA(candles, 20), color: SMA_20_COLOR });
    if (showEMA50) lines.push({ key: "ema50", data: computeEMA(candles, 50), color: EMA_50_COLOR });
    if (showVWAP) lines.push({ key: "vwap", data: computeVWAP(candles), color: VWAP_COLOR });
    return lines;
  }, [candles, showSMA7, showSMA20, showEMA50, showVWAP]);

  return (
    <>
      <PanelWrapper panelKey="candlestick">
        <div className="bg-black border border-[#1a1a1a] rounded-2xl overflow-hidden">
          <ChartHeader coin={coin} interval={interval} onIntervalChange={onIntervalChange} />
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
              No candle data for {coin}.
            </p>
          )}
        </div>
      </PanelWrapper>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* OI panel — only in compare mode; single-coin OI lives in the candle sub-pane */}
        {comparing && (
          <PanelWrapper panelKey="oi-chart">
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
          </PanelWrapper>
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
        <TopHoldersTable coin={coin} positions={topCoinPositions} />
      </PanelWrapper>

      <PanelWrapper panelKey="top-traders">
        <TopTradersTable coin={coin} hours={hours} traders={topWhales} />
      </PanelWrapper>
    </>
  );
}
