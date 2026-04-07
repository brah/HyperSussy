import { memo, useEffect } from "react";
import { AreaSeries, createChart, type Time } from "lightweight-charts";
import type { OISnapshotItem } from "../../api/types";
import { compareColors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatUSD } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

export type OIMode = "pct" | "usd";

export interface OISeries {
  data: OISnapshotItem[];
  label: string;
}

interface OIChartProps {
  series: OISeries[];
  mode?: OIMode;
  height?: number;
}

function toPercent(items: OISnapshotItem[]): { time: Time; value: number }[] {
  if (items.length === 0) return [];
  const base = items[0].open_interest_usd;
  if (base === 0) return items.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: 0 }));
  return items.map((d) => ({
    time: msToSec(d.timestamp_ms) as Time,
    value: ((d.open_interest_usd - base) / base) * 100,
  }));
}

function toUsd(items: OISnapshotItem[]): { time: Time; value: number }[] {
  return items.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.open_interest_usd }));
}

const pctFormat = { type: "custom" as const, formatter: (v: number) => `${v.toFixed(2)}%`, minMove: 0.001 };
const usdFormat = { type: "custom" as const, formatter: (v: number) => formatUSD(v), minMove: 0.01 };

/** Multi-coin OI comparison — % change from window start (default) or raw USD. */
export const OIChart = memo(function OIChart({
  series,
  mode = "pct",
  height = 260,
}: Readonly<OIChartProps>) {
  const [containerRef, width] = useContainerWidth();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || series.length === 0) return;

    const chart = createChart(el, lwcChartOptions(width, height));
    const priceFormat = mode === "usd" ? usdFormat : pctFormat;

    series.forEach(({ data, label }, i) => {
      const color = compareColors[i % compareColors.length];
      chart.addSeries(AreaSeries, {
        lineColor: color,
        topColor: color + "40",
        bottomColor: color + "00",
        lineWidth: 2,
        lineStyle: i === 0 ? 0 : 2,
        priceFormat,
        title: label,
      }).setData(mode === "usd" ? toUsd(data) : toPercent(data));
    });

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, series, mode]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
