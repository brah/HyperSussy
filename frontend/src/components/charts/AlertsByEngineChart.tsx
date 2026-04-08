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
import { tooltipStyle } from "../../theme/chartDefaults";
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

  // Container div is rendered unconditionally so the ref attaches on
  // first commit and useContainerWidth's ResizeObserver actually
  // installs — see MarkOracleChart for the same fix and explanation.
  // The BarChart inside is gated on both width and data length so we
  // never render an empty BarChart.
  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && data.length > 0 && (
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
          <Tooltip contentStyle={tooltipStyle} />
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
