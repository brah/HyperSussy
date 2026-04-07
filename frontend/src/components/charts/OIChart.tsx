import { memo, useMemo } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { OISnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatUSD } from "../../utils/format";
import { mergeTimeSeries } from "../../utils/timeseries";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface OIChartProps {
  data: OISnapshotItem[];
  height?: number;
  label1?: string;
  data2?: OISnapshotItem[];
  label2?: string;
}

/** Normalise a series to % change from its first point. */
function toPercent(series: OISnapshotItem[]): Array<{ timestamp_ms: number; pct: number }> {
  if (series.length === 0) return [];
  const base = series[0].open_interest_usd;
  if (base === 0) return series.map((d) => ({ timestamp_ms: d.timestamp_ms, pct: 0 }));
  return series.map((d) => ({
    timestamp_ms: d.timestamp_ms,
    pct: ((d.open_interest_usd - base) / base) * 100,
  }));
}

export const OIChart = memo(function OIChart({
  data,
  height = 260,
  label1,
  data2,
  label2,
}: Readonly<OIChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const comparing = data2 != null && data2.length > 0;

  const merged = useMemo(() => {
    if (!comparing || data2 == null) return null;
    return mergeTimeSeries(toPercent(data), toPercent(data2), "pct", "pct2");
  }, [comparing, data, data2]);

  if (comparing && merged !== null) {
    return (
      <div ref={containerRef} style={{ width: "100%", height }}>
        {width > 0 && (
          <ComposedChart width={width} height={height} data={merged} margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id="oi-grad1" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.teal} stopOpacity={0.2} />
                <stop offset="95%" stopColor={colors.teal} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="oi-grad2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.orange} stopOpacity={0.15} />
                <stop offset="95%" stopColor={colors.orange} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis
              dataKey="timestamp_ms"
              tickFormatter={(v: number) => fmtTime(v)}
              stroke={colors.grey}
              tick={{ fill: colors.grey, fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              stroke={colors.grey}
              tick={{ fill: colors.grey, fontSize: 11 }}
              width={60}
            />
            <Tooltip
              formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name]}
              labelFormatter={(ms: number) => fmtTime(ms)}
              contentStyle={{
                background: colors.bg,
                border: `1px solid ${colors.grid}`,
                boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
                color: colors.text,
                fontSize: 12,
              }}
            />
            <Legend
              formatter={(value) => (
                <span style={{ color: colors.text, fontSize: 12 }}>{value}</span>
              )}
            />
            <Area
              type="monotone"
              dataKey="pct"
              name={label1 ?? "Primary"}
              stroke={colors.teal}
              fill="url(#oi-grad1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="pct2"
              name={label2 ?? "Compare"}
              stroke={colors.orange}
              fill="url(#oi-grad2)"
              strokeWidth={2}
              strokeDasharray="4 2"
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        )}
      </div>
    );
  }

  // Single-coin mode: OI area + mark price line on right axis
  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && (
        <ComposedChart width={width} height={height} data={data} margin={{ top: 4, right: 72, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="oi-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={colors.teal} stopOpacity={0.25} />
              <stop offset="95%" stopColor={colors.teal} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="timestamp_ms"
            tickFormatter={(v: number) => fmtTime(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            minTickGap={60}
          />
          <YAxis
            yAxisId="oi"
            tickFormatter={(v: number) => formatUSD(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            width={72}
          />
          <YAxis
            yAxisId="price"
            orientation="right"
            tickFormatter={(v: number) => formatUSD(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            width={72}
          />
          <Tooltip
            formatter={(v: number, name: string) => [formatUSD(v), name]}
            labelFormatter={(ms: number) => fmtTime(ms)}
            contentStyle={{
              background: colors.bg,
              border: `1px solid ${colors.grid}`,
              boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
              color: colors.text,
              fontSize: 12,
            }}
          />
          <Area
            yAxisId="oi"
            type="monotone"
            dataKey="open_interest_usd"
            name="OI (USD)"
            stroke={colors.teal}
            fill="url(#oi-grad)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            yAxisId="price"
            type="monotone"
            dataKey="mark_price"
            name="Price"
            stroke={colors.orange}
            strokeWidth={1.5}
            strokeDasharray="4 2"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      )}
    </div>
  );
});
