import { memo } from "react";
import { LineSeries, type Time } from "lightweight-charts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { msToSec } from "../../theme/chartDefaults";
import { formatPrice } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";
import { useLightweightChart } from "../../hooks/useLightweightChart";

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

  useLightweightChart(
    containerRef,
    width,
    height,
    (chart) => {
      if (data.length === 0) return;
      chart
        .addSeries(LineSeries, {
          color: colors.teal,
          lineWidth: 2,
          priceFormat,
          title: "Mark",
        })
        .setData(
          data.map((d) => ({
            time: msToSec(d.timestamp_ms) as Time,
            value: d.mark_price,
          })),
        );

      chart
        .addSeries(LineSeries, {
          color: colors.orange,
          lineWidth: 1,
          lineStyle: 2,
          priceFormat,
          title: "Oracle",
        })
        .setData(
          data.map((d) => ({
            time: msToSec(d.timestamp_ms) as Time,
            value: d.oracle_price,
          })),
        );
    },
    [data],
    { leftPriceScale: { borderColor: colors.grid, visible: false } },
  );

  // The container div is rendered unconditionally so the ref attaches
  // on the very first commit. Callers handle the empty/loading branches
  // externally; this component just owns the chart lifecycle.
  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
