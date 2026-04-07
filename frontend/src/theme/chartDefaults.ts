/**
 * Shared chart defaults — defined at module scope so every chart that imports
 * them gets a stable object/function reference. Inline object literals and
 * arrow functions in JSX are recreated on every render, causing recharts to
 * treat them as changed props and re-run its internal tick/layout pipeline.
 */
import { ColorType, CrosshairMode, LineStyle, type DeepPartial, type ChartOptions, type Time } from "lightweight-charts";
import { colors } from "./colors";
import { fmtTime, msToSec } from "../utils/time";

export { LineStyle, msToSec };

/**
 * Base options for all lightweight-charts panel charts (OI, Funding, etc.).
 * Canvas-based, so zero forced-DOM-layout reads on mount or update.
 */
export function lwcChartOptions(width: number, height: number): DeepPartial<ChartOptions> {
  return {
    width,
    height,
    layout: {
      background: { type: ColorType.Solid, color: colors.bg },
      textColor: colors.grey,
      fontFamily: "ui-monospace, SFMono-Regular, monospace",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: colors.grid },
      horzLines: { color: colors.grid },
    },
    timeScale: {
      borderColor: colors.grid,
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (t: Time) => fmtTime((t as number) * 1000),
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { labelBackgroundColor: colors.text },
      horzLine: { labelBackgroundColor: colors.text },
    },
    rightPriceScale: { borderColor: colors.grid },
    leftPriceScale: { borderColor: colors.grid },
    handleScroll: false,
    handleScale: false,
  };
}

/** Tooltip contentStyle shared across all recharts charts. */
export const tooltipStyle = {
  background: colors.bg,
  border: `1px solid ${colors.grid}`,
  boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
  color: colors.text,
  fontSize: 12,
} as const;

/**
 * Tooltip labelFormatter for timestamp_ms axes.
 * Accepts `unknown` so it satisfies recharts' ReactNode label type without
 * a type error, while still doing the correct numeric cast at runtime.
 */
export function fmtTimestampLabel(label: unknown): string {
  return fmtTime(label as number);
}

/**
 * Tooltip labelFormatter that passes the label through unchanged.
 * Used for category axes (address, type) where the raw value is the label.
 */
export function fmtPassthroughLabel(label: unknown): React.ReactNode {
  return label as React.ReactNode;
}
