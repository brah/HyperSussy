import { memo, useEffect } from "react";
import { HistogramSeries, LineSeries, createChart, type Time } from "lightweight-charts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors, compareColors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatFundingRate } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

export interface FundingSeries {
  data: FundingSnapshotItem[];
  label: string;
}

interface FundingChartProps {
  /** Primary coin — always shown as a coloured histogram. */
  data: FundingSnapshotItem[];
  label?: string;
  /** Additional coins — each rendered as a dashed line. */
  compares?: FundingSeries[];
  height?: number;
}

const rateFormat = {
  type: "custom" as const,
  formatter: (v: number) => formatFundingRate(v),
  minMove: 0.000001,
};

export const FundingChart = memo(function FundingChart({
  data,
  label,
  compares = [],
  height = 220,
}: Readonly<FundingChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const comparing = compares.length > 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || data.length === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      rightPriceScale: { borderColor: colors.grid, visible: true },
    });

    // Primary: funding rate histogram coloured by sign.
    chart.addSeries(HistogramSeries, {
      priceFormat: rateFormat,
      title: label ?? "Funding",
    }).setData(
      data.map((d) => ({
        time: msToSec(d.timestamp_ms) as Time,
        value: d.funding_rate,
        color: d.funding_rate >= 0 ? colors.teal : colors.red,
      })),
    );

    if (comparing) {
      // Compare mode: one dashed line per extra coin.
      compares.forEach(({ data: cData, label: cLabel }, i) => {
        const color = compareColors[i + 1] ?? colors.grey;
        chart.addSeries(LineSeries, {
          color,
          lineWidth: 1,
          lineStyle: 2,
          priceFormat: rateFormat,
          title: cLabel,
        }).setData(
          cData.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.funding_rate })),
        );
      });
    } else {
      // Single mode: premium as a subtle dashed line.
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
  }, [width, height, data, compares, comparing, label]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
