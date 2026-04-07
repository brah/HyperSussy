import { memo, useEffect, useMemo } from "react";
import { HistogramSeries, createChart, type Time } from "lightweight-charts";
import type { TradeFlowItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatUSD } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface TradeFlowChartProps {
  data: TradeFlowItem[];
  height?: number;
}

interface BucketRow {
  bucket: number;
  buy: number;
  sell: number;
}

function pivotFlow(data: TradeFlowItem[]): BucketRow[] {
  const byBucket = new Map<number, BucketRow>();
  for (const row of data) {
    const existing = byBucket.get(row.bucket) ?? { bucket: row.bucket, buy: 0, sell: 0 };
    if (row.side === "B") existing.buy += row.volume_usd;
    else existing.sell += row.volume_usd;
    byBucket.set(row.bucket, existing);
  }
  return [...byBucket.values()].sort((a, b) => a.bucket - b.bucket);
}

const volFormat = {
  type: "custom" as const,
  formatter: (v: number) => formatUSD(Math.abs(v)),
  minMove: 0.01,
};

/**
 * Buy vs sell volume per time bucket.
 * Buy bars rise above zero (teal), sell bars fall below (red).
 * This matches the convention used by professional trading terminals.
 */
export const TradeFlowChart = memo(function TradeFlowChart({
  data,
  height = 220,
}: Readonly<TradeFlowChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const pivoted = useMemo(() => pivotFlow(data), [data]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || pivoted.length === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      leftPriceScale: { borderColor: colors.grid, visible: false },
    });

    // Buy: positive bars (teal)
    chart.addSeries(HistogramSeries, {
      color: colors.teal,
      priceFormat: volFormat,
      title: "Buy",
    }).setData(
      pivoted.map((b) => ({ time: msToSec(b.bucket) as Time, value: b.buy })),
    );

    // Sell: negative bars (red) — visually mirror below zero
    chart.addSeries(HistogramSeries, {
      color: colors.red,
      priceFormat: volFormat,
      title: "Sell",
    }).setData(
      pivoted.map((b) => ({ time: msToSec(b.bucket) as Time, value: -b.sell })),
    );

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, pivoted]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
