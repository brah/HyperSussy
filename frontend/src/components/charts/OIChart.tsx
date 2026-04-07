import { memo, useEffect } from "react";
import { AreaSeries, LineSeries, createChart, type Time } from "lightweight-charts";
import type { OISnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { lwcChartOptions, msToSec } from "../../theme/chartDefaults";
import { formatUSD } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface OIChartProps {
  data: OISnapshotItem[];
  height?: number;
  label1?: string;
  data2?: OISnapshotItem[];
  label2?: string;
}

function toPercent(series: OISnapshotItem[]): { time: Time; value: number }[] {
  if (series.length === 0) return [];
  const base = series[0].open_interest_usd;
  if (base === 0) return series.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: 0 }));
  return series.map((d) => ({
    time: msToSec(d.timestamp_ms) as Time,
    value: ((d.open_interest_usd - base) / base) * 100,
  }));
}

const usdFormat = { type: "custom" as const, formatter: (v: number) => formatUSD(v), minMove: 0.01 };
const pctFormat = { type: "custom" as const, formatter: (v: number) => `${v.toFixed(2)}%`, minMove: 0.001 };

export const OIChart = memo(function OIChart({
  data,
  height = 260,
  label1,
  data2,
  label2,
}: Readonly<OIChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const comparing = data2 != null && data2.length > 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0 || data.length === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      leftPriceScale: { borderColor: colors.grid, visible: !comparing },
    });

    if (comparing && data2 != null) {
      // Normalise both series to % change so they share a single scale.
      chart.addSeries(AreaSeries, {
        lineColor: colors.teal,
        topColor: colors.teal + "40",
        bottomColor: colors.teal + "00",
        lineWidth: 2,
        priceFormat: pctFormat,
        title: label1 ?? "Primary",
      }).setData(toPercent(data));

      chart.addSeries(AreaSeries, {
        lineColor: colors.orange,
        topColor: colors.orange + "26",
        bottomColor: colors.orange + "00",
        lineWidth: 2,
        lineStyle: 2,
        priceFormat: pctFormat,
        title: label2 ?? "Compare",
      }).setData(toPercent(data2));
    } else {
      // Single coin: OI area on the left scale, mark price line on the right.
      chart.addSeries(AreaSeries, {
        priceScaleId: "left",
        lineColor: colors.teal,
        topColor: colors.teal + "40",
        bottomColor: colors.teal + "00",
        lineWidth: 2,
        priceFormat: usdFormat,
        title: "OI",
      }).setData(
        data.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.open_interest_usd })),
      );

      chart.addSeries(LineSeries, {
        priceScaleId: "right",
        color: colors.orange,
        lineWidth: 1,
        lineStyle: 2,
        priceFormat: usdFormat,
        title: "Price",
      }).setData(
        data.map((d) => ({ time: msToSec(d.timestamp_ms) as Time, value: d.mark_price })),
      );
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [width, height, data, data2, comparing, label1, label2]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
