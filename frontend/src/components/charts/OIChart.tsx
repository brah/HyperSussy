import { memo, useEffect } from "react";
import { AreaSeries, createChart, type Time } from "lightweight-charts";
import type { OISnapshotItem } from "../../api/types";
import { compareColors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { useContainerWidth } from "../../hooks/useContainerWidth";

export interface OISeries {
  data: OISnapshotItem[];
  label: string;
}

interface OIChartProps {
  series: OISeries[];
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

const pctFormat = { type: "custom" as const, formatter: (v: number) => `${v.toFixed(2)}%`, minMove: 0.001 };

/** Multi-coin OI comparison — all series normalised to % change from window start. */
export const OIChart = memo(function OIChart({
  series,
  height = 260,
}: Readonly<OIChartProps>) {
  const [containerRef, width] = useContainerWidth();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || series.length === 0) return;

    const chart = createChart(el, lwcChartOptions(width, height));

    series.forEach(({ data, label }, i) => {
      const color = compareColors[i % compareColors.length];
      chart.addSeries(AreaSeries, {
        lineColor: color,
        topColor: color + "40",
        bottomColor: color + "00",
        lineWidth: 2,
        lineStyle: i === 0 ? 0 : 2,
        priceFormat: pctFormat,
        title: label,
      }).setData(toPercent(data));
    });

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, series]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
