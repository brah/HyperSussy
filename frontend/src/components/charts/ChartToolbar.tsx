import { memo } from "react";
import { useIndicator, useIndicatorStore } from "../../stores/indicatorStore";
import {
  SMA_7_COLOR,
  SMA_20_COLOR,
  EMA_50_COLOR,
  VWAP_COLOR,
} from "../../utils/indicators";
import { colors } from "../../theme/colors";

interface IndicatorDef {
  key: string;
  label: string;
  color: string;
  defaultOn?: boolean;
}

const PRICE_OVERLAYS: IndicatorDef[] = [
  { key: "sma7", label: "SMA 7", color: SMA_7_COLOR },
  { key: "sma20", label: "SMA 20", color: SMA_20_COLOR, defaultOn: true },
  { key: "ema50", label: "EMA 50", color: EMA_50_COLOR },
  { key: "vwap", label: "VWAP", color: VWAP_COLOR },
];

const PANE_OVERLAYS: IndicatorDef[] = [
  { key: "oi", label: "OI", color: colors.teal, defaultOn: true },
  { key: "funding", label: "Funding", color: colors.grey },
];

/** Single pill — subscribes only to its own indicator key. */
const IndicatorPill = memo(function IndicatorPill({
  indicatorKey,
  label,
  color,
  defaultOn = false,
}: Readonly<{
  indicatorKey: string;
  label: string;
  color: string;
  defaultOn?: boolean;
}>) {
  const active = useIndicator(indicatorKey, defaultOn);
  const toggle = useIndicatorStore((s) => s.toggle);

  return (
    <button
      onClick={() => toggle(indicatorKey, defaultOn)}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px]
                  font-mono uppercase tracking-wide transition-colors ${
                    active
                      ? "bg-gray-800 text-gray-100 border border-gray-600"
                      : "bg-transparent text-gray-500 border border-gray-800 hover:text-gray-300 hover:border-gray-700"
                  }`}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: active ? color : "#374151" }}
      />
      {label}
    </button>
  );
});

/** Horizontal row of indicator toggle pills for the candlestick chart. */
export const ChartToolbar = memo(function ChartToolbar() {
  return (
    <div className="flex flex-wrap items-center gap-1 px-3 py-1.5 bg-black border-b border-[#1a1a1a]">
      {PRICE_OVERLAYS.map((d) => (
        <IndicatorPill
          key={d.key}
          indicatorKey={d.key}
          label={d.label}
          color={d.color}
          defaultOn={d.defaultOn}
        />
      ))}
      <span className="mx-1 h-3 border-r border-gray-700" />
      {PANE_OVERLAYS.map((d) => (
        <IndicatorPill
          key={d.key}
          indicatorKey={d.key}
          label={d.label}
          color={d.color}
          defaultOn={d.defaultOn}
        />
      ))}
    </div>
  );
});
