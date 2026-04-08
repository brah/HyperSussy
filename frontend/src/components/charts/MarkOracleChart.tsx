import { memo, useEffect } from "react";
import { LineSeries, createChart, type Time } from "lightweight-charts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatPrice } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface MarkOracleChartProps {
  data: FundingSnapshotItem[];
  height?: number;
}

const priceFormat = {
  type: "custom" as const,
  formatter: (v: number) => formatPrice(v),
  minMove: 0.001,
};

/** Mark price vs oracle price over time — two line series on a shared scale. */
export const MarkOracleChart = memo(function MarkOracleChart({
  data,
  height = 240,
}: Readonly<MarkOracleChartProps>) {
  const [containerRef, width] = useContainerWidth();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || data.length === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      leftPriceScale: { borderColor: colors.grid, visible: false },
    });

    chart.addSeries(LineSeries, {
      color: colors.teal,
      lineWidth: 2,
      priceFormat,
      title: "Mark",
    }).setData(
      data.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.mark_price })),
    );

    chart.addSeries(LineSeries, {
      color: colors.orange,
      lineWidth: 1,
      lineStyle: 2,
      priceFormat,
      title: "Oracle",
    }).setData(
      data.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.oracle_price })),
    );

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, data]);

  // The container div is rendered unconditionally so the ref attaches
  // on the very first commit. An earlier early-return on empty data
  // skipped the ref entirely, which prevented `useContainerWidth`'s
  // ResizeObserver from ever installing — `width` then stayed at 0
  // forever, the chart effect bailed forever, and the panel rendered
  // empty. Callers like CoinView handle the empty/loading branches
  // externally; this component just owns the chart lifecycle.
  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
