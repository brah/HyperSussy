import { memo } from "react";
import { useWsStore } from "../../api/websocket";
import { formatPrice, formatUSD, formatFundingRate } from "../../utils/format";
import { INTERVAL_OPTIONS, type Interval } from "../common/IntervalSelector";

interface ChartHeaderProps {
  coin: string;
  interval: Interval;
  onIntervalChange: (iv: Interval) => void;
}

/**
 * Dense, dark-themed header bar above the candlestick chart.
 * Mirrors the layout of pro trading terminals: symbol • interval • exchange |
 * Funding • Mark price | OI • 24h volume.
 */
export const ChartHeader = memo(function ChartHeader({
  coin,
  interval,
  onIntervalChange,
}: Readonly<ChartHeaderProps>) {
  const snapshot = useWsStore((s) => s.snapshots[coin]);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-xs font-mono border-b border-[#1a1a1a] bg-black">
      <div className="flex items-center gap-2">
        <span className="text-white font-semibold text-sm">{coin}USD</span>
        <span className="text-gray-500">·</span>
        <div className="flex items-center gap-0.5">
          {INTERVAL_OPTIONS.map((iv) => (
            <button
              key={iv}
              onClick={() => onIntervalChange(iv)}
              className={`px-1.5 py-0.5 rounded text-[11px] font-mono transition-colors ${
                interval === iv
                  ? "bg-gray-700 text-white"
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
              }`}
            >
              {iv}
            </button>
          ))}
        </div>
        <span className="text-gray-500">·</span>
        <span className="text-gray-400 uppercase tracking-wide">Hyperliquid</span>
      </div>

      {snapshot && (
        <>
          <span className="h-3 border-r border-gray-700" />
          <Stat label="Mark" value={formatPrice(snapshot.mark_price)} />
          <Stat
            label="Funding"
            value={formatFundingRate(snapshot.funding_rate)}
            tone={snapshot.funding_rate >= 0 ? "pos" : "neg"}
          />
          <Stat
            label="Premium"
            value={formatFundingRate(snapshot.premium)}
            tone={snapshot.premium >= 0 ? "pos" : "neg"}
          />
          <span className="h-3 border-r border-gray-700" />
          <Stat label="OI" value={formatUSD(snapshot.open_interest_usd)} />
          <Stat label="24h Vol" value={formatUSD(snapshot.day_volume_usd)} />
        </>
      )}
    </div>
  );
});

function Stat({
  label,
  value,
  tone,
}: Readonly<{ label: string; value: string; tone?: "pos" | "neg" }>) {
  const valueClass =
    tone === "pos" ? "text-emerald-400" : tone === "neg" ? "text-red-400" : "text-gray-200";
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-gray-500 uppercase tracking-wide text-[10px]">{label}</span>
      <span className={`tabular-nums ${valueClass}`}>{value}</span>
    </span>
  );
}
