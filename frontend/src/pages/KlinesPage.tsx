import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  candlesQuery,
  coinsQuery,
  topHoldersQuery,
  topWhalesQuery,
  tradeFlowQuery,
} from "../api/queries";
import { CoinSelector } from "../components/common/CoinSelector";
import { CandlestickChart } from "../components/charts/CandlestickChart";
import { TopHoldersChart } from "../components/charts/TopHoldersChart";
import { TradeFlowChart } from "../components/charts/TradeFlowChart";
import { PageHeader } from "../components/layout/PageHeader";
import { AddressLink } from "../components/common/AddressLink";
import { formatUSD } from "../utils/format";

const INTERVAL_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
type Interval = (typeof INTERVAL_OPTIONS)[number];

const HOURS_FOR_INTERVAL: Record<Interval, number> = {
  "1m": 4,
  "5m": 12,
  "15m": 24,
  "1h": 48,
  "4h": 120,
  "1d": 720,
};

export function KlinesPage() {
  const [coin, setCoin] = useState("BTC");
  const [interval, setInterval] = useState<Interval>("1h");

  const candleHours = HOURS_FOR_INTERVAL[interval];

  const { data: coins = [] } = useQuery(coinsQuery());
  const { data: candles = [] } = useQuery(
    candlesQuery(coin, interval, candleHours)
  );
  const { data: topHolders = [] } = useQuery(topHoldersQuery(coin, 24, 15));
  const { data: tradeFlow = [] } = useQuery(tradeFlowQuery(coin, 24));
  const { data: topWhales = [] } = useQuery(topWhalesQuery(coin, 1));

  return (
    <div>
      <PageHeader title="Klines">
        <CoinSelector coins={coins} value={coin} onChange={setCoin} />
        <select
          value={interval}
          onChange={(e) => setInterval(e.target.value as Interval)}
          className="bg-[#141a22] border border-[#2a2d35] text-[#fafafa] text-sm
                     rounded px-3 py-1.5 focus:outline-none focus:border-[#00d4aa]"
        >
          {INTERVAL_OPTIONS.map((iv) => (
            <option key={iv} value={iv}>
              {iv}
            </option>
          ))}
        </select>
      </PageHeader>

      <div className="space-y-6">
        {/* Candlestick chart */}
        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
          <h2 className="text-[#fafafa] font-medium mb-3">
            {coin} / {interval}
          </h2>
          {candles.length > 0 ? (
            <CandlestickChart candles={candles} height={380} />
          ) : (
            <p className="text-[#4a4e69] text-sm py-8 text-center">
              No candle data for {coin} ({interval}).
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Top holders concentration */}
          <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
            <h2 className="text-[#fafafa] font-medium mb-3">
              Top Holder Concentration — 24h
            </h2>
            {topHolders.length > 0 ? (
              <TopHoldersChart data={topHolders} />
            ) : (
              <p className="text-[#4a4e69] text-sm py-8 text-center">No data.</p>
            )}
          </div>

          {/* Trade flow */}
          <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
            <h2 className="text-[#fafafa] font-medium mb-3">
              Trade Flow — 24h
            </h2>
            {tradeFlow.length > 0 ? (
              <TradeFlowChart data={tradeFlow} />
            ) : (
              <p className="text-[#4a4e69] text-sm py-8 text-center">No data.</p>
            )}
          </div>
        </div>

        {/* Top whales table */}
        {topWhales.length > 0 && (
          <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
            <h2 className="text-[#fafafa] font-medium mb-3">
              Top Traders — {coin} (1h)
            </h2>
            <div className="divide-y divide-[#2a2d35]">
              {topWhales.slice(0, 10).map((w, idx) => (
                <div
                  key={w.address}
                  className="flex items-center justify-between py-2"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-[#4a4e69] text-sm w-5">
                      {idx + 1}
                    </span>
                    <AddressLink address={w.address} />
                  </div>
                  <span className="text-[#fafafa] tabular-nums text-sm">
                    {formatUSD(w.volume_usd)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
