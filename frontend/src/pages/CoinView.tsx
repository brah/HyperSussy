/**
 * Coin analytics view — lazy-loaded by MarketPage so that recharts and
 * lightweight-charts are NOT included in the initial bundle. The split
 * means the root dashboard loads without pulling in ~550 kB of chart
 * libraries; they are only fetched when the user selects a coin.
 */

import { useMemo } from "react";
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
import { OIChart } from "../components/charts/OIChart";
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
import type { Interval } from "../components/common/IntervalSelector";
import type { Hours } from "../components/common/HoursSelector";

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
  coin2: string;
  interval: Interval;
  hours: Hours;
  onIntervalChange: (iv: Interval) => void;
}

export default function CoinView({ coin, coin2, interval, hours, onIntervalChange }: Readonly<CoinViewProps>) {
  const candleHours = HOURS_FOR_INTERVAL[interval];
  const compare = coin2 !== "" && coin2 !== coin;

  const { data: candles = [] } = useQuery(candlesQuery(coin, interval, candleHours));
  const { data: oiData = [] } = useQuery(oiQuery(coin, hours));
  const { data: fundingData = [] } = useQuery(fundingQuery(coin, hours));
  const { data: topHolders = [] } = useQuery(topHoldersQuery(coin, hours, 15));
  const { data: topCoinPositions = [] } = useQuery(topCoinPositionsQuery(coin, 25));
  const { data: tradeFlow = [] } = useQuery(tradeFlowQuery(coin, hours));
  const { data: topWhales = [] } = useQuery(topWhalesQuery(coin, hours));
  const { data: oiData2 = [] } = useQuery({ ...oiQuery(coin2, hours), enabled: compare });
  const { data: fundingData2 = [] } = useQuery({ ...fundingQuery(coin2, hours), enabled: compare });

  // Indicator toggles
  const showSMA7 = useIndicator("sma7");
  const showSMA20 = useIndicator("sma20", true);
  const showEMA50 = useIndicator("ema50");
  const showVWAP = useIndicator("vwap");
  const showOI = useIndicator("oi");
  const showFunding = useIndicator("funding");

  // OI/funding spanning the candle window — only fetched when the indicator is on
  const { data: oiForChart = [] } = useQuery({
    ...oiQuery(coin, candleHours),
    enabled: showOI,
  });
  const { data: fundingForChart = [] } = useQuery({
    ...fundingQuery(coin, candleHours),
    enabled: showFunding,
  });

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
          <ChartHeader
            coin={coin}
            interval={interval}
            onIntervalChange={onIntervalChange}
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
            title={"Open Interest" + (compare ? " \u2014 " + coin + " vs " + coin2 : "") + " \u2014 " + hours + "h"}
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
            title={"Funding Rate" + (compare ? " \u2014 " + coin + " vs " + coin2 : "") + " \u2014 " + hours + "h"}
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
  );
}
