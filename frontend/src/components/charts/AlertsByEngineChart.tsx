import { memo, useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { colors } from "../../theme/colors";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface AlertsByEngineChartProps {
  counts: Record<string, number>;
  height?: number;
}

/** Horizontal bar chart showing alert counts by engine/type. */
export const AlertsByEngineChart = memo(function AlertsByEngineChart({
  counts,
  height = 180,
}: Readonly<AlertsByEngineChartProps>) {
  const [containerRef, width] = useContainerWidth();

  const data = useMemo(
    () =>
      Object.entries(counts)
        .map(([type, count]) => ({ type, count }))
        .sort((a, b) => b.count - a.count),
    [counts]
  );

  if (data.length === 0) return null;

  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && (
        <BarChart
          width={width}
          height={height}
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 16, bottom: 0, left: 120 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={colors.grid}
            horizontal={false}
          />
          <XAxis
            type="number"
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
          />
          <YAxis
            type="category"
            dataKey="type"
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            width={116}
          />
          <Tooltip
            contentStyle={{
              background: colors.bg,
              border: `1px solid ${colors.grid}`,
              boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
              color: colors.text,
              fontSize: 12,
            }}
          />
          <Bar
            dataKey="count"
            fill={colors.teal}
            isAnimationActive={false}
            radius={[0, 2, 2, 0]}
          />
        </BarChart>
      )}
    </div>
  );
});
