import { memo } from "react";
import { HistogramSeries, LineSeries, type Time } from "lightweight-charts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors, compareColors } from "../../theme/colors";
import { msToSec } from "../../theme/chartDefaults";
import { formatFundingRate } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";
import { useLightweightChart } from "../../hooks/useLightweightChart";

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

  useLightweightChart(
    containerRef,
    width,
    height,
    (chart) => {
      if (data.length === 0) return;
      chart
        .addSeries(HistogramSeries, {
          priceFormat: rateFormat,
          title: label ?? "Funding",
        })
        .setData(
          data.map((d) => ({
            time: msToSec(d.timestamp_ms) as Time,
            value: d.funding_rate,
            color: d.funding_rate >= 0 ? colors.teal : colors.red,
          })),
        );

      if (comparing) {
        compares.forEach(({ data: cData, label: cLabel }, i) => {
          const color = compareColors[i + 1] ?? colors.grey;
          chart
            .addSeries(LineSeries, {
              color,
              lineWidth: 1,
              lineStyle: 2,
              priceFormat: rateFormat,
              title: cLabel,
            })
            .setData(
              cData.map((d) => ({
                time: msToSec(d.timestamp_ms) as Time,
                value: d.funding_rate,
              })),
            );
        });
      } else {
        chart
          .addSeries(LineSeries, {
            color: colors.orange,
            lineWidth: 1,
            lineStyle: 2,
            priceFormat: rateFormat,
            title: "Premium",
          })
          .setData(
            data.map((d) => ({
              time: msToSec(d.timestamp_ms) as Time,
              value: d.premium,
            })),
          );
      }
    },
    [data, compares, comparing, label],
    { rightPriceScale: { borderColor: colors.grid, visible: true } },
  );

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
