import { memo, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatPrice } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface MarkOracleChartProps {
  data: FundingSnapshotItem[];
  height?: number;
}

/** Dual-line chart comparing mark price vs oracle price over time. */
export const MarkOracleChart = memo(function MarkOracleChart({
  data,
  height = 240,
}: Readonly<MarkOracleChartProps>) {
  const [containerRef, width] = useContainerWidth();

  const chartData = useMemo(
    () =>
      data.map((d) => ({
        timestamp_ms: d.timestamp_ms,
        mark: d.mark_price,
        oracle: d.oracle_price,
      })),
    [data]
  );

  if (chartData.length === 0) {
    return (
      <p className="text-hs-grey text-sm py-6 text-center">No data.</p>
    );
  }

  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && (
        <LineChart
          width={width}
          height={height}
          data={chartData}
          margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="timestamp_ms"
            tickFormatter={(v: number) => fmtTime(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            minTickGap={60}
          />
          <YAxis
            tickFormatter={(v: number) => formatPrice(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            width={80}
            domain={["auto", "auto"]}
          />
          <Tooltip
            formatter={(v: number, name: string) => [
              formatPrice(v),
              name === "mark" ? "Mark" : "Oracle",
            ]}
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
            wrapperStyle={{ fontSize: 12, color: colors.grey }}
            formatter={(v: string) => (v === "mark" ? "Mark" : "Oracle")}
          />
          <Line
            type="monotone"
            dataKey="mark"
            stroke={colors.teal}
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="oracle"
            stroke={colors.orange}
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="4 2"
            isAnimationActive={false}
          />
        </LineChart>
      )}
    </div>
  );
});
