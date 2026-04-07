import { memo, useEffect } from "react";
import { HistogramSeries, LineSeries, createChart, type Time } from "lightweight-charts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatFundingRate } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface FundingChartProps {
  data: FundingSnapshotItem[];
  height?: number;
  label1?: string;
  data2?: FundingSnapshotItem[];
  label2?: string;
}

const rateFormat = {
  type: "custom" as const,
  formatter: (v: number) => formatFundingRate(v),
  minMove: 0.000001,
};

export const FundingChart = memo(function FundingChart({
  data,
  height = 220,
  label1,
  data2,
  label2,
}: Readonly<FundingChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const comparing = data2 != null && data2.length > 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || data.length === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      leftPriceScale: { borderColor: colors.grid, visible: false },
      rightPriceScale: { borderColor: colors.grid, visible: true },
    });

    // Primary: funding rate histogram coloured by sign.
    chart.addSeries(HistogramSeries, {
      priceFormat: rateFormat,
      title: label1 ?? "Funding",
    }).setData(
      data.map((d) => ({
        time: msToSec(d.timestamp_ms) as Time,
        value: d.funding_rate,
        color: d.funding_rate >= 0 ? colors.teal : colors.red,
      })),
    );

    // Secondary: premium line (single mode) or compare coin line.
    if (comparing && data2 != null) {
      chart.addSeries(LineSeries, {
        color: colors.orange,
        lineWidth: 1,
        lineStyle: 2,
        priceFormat: rateFormat,
        title: label2 ?? "Compare",
      }).setData(
        data2.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.funding_rate })),
      );
    } else {
      chart.addSeries(LineSeries, {
        color: colors.orange,
        lineWidth: 1,
        lineStyle: 2,
        priceFormat: rateFormat,
        title: "Premium",
      }).setData(
        data.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.premium })),
      );
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, data, data2, comparing, label1, label2]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
