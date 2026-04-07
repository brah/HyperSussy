import { memo, useMemo } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatFundingRate } from "../../utils/format";
import { mergeTimeSeries } from "../../utils/timeseries";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface FundingChartProps {
  data: FundingSnapshotItem[];
  height?: number;
  label1?: string;
  data2?: FundingSnapshotItem[];
  label2?: string;
}

/**
 * Bar shape that colours each bar by the sign of its funding_rate value.
 * Replaces the deprecated Cell child pattern from recharts v2.
 */
function FundingBar(props: Record<string, unknown>) {
  const { x, y, width, height, value } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    value: number;
  };
  if (!width || !height) return null;
  const fill = value >= 0 ? colors.teal : colors.red;
  return <rect x={x} y={y} width={Math.max(0, width)} height={Math.max(0, height)} fill={fill} />;
}

export const FundingChart = memo(function FundingChart({
  data,
  height = 220,
  label1,
  data2,
  label2,
}: Readonly<FundingChartProps>) {
  const [containerRef, width] = useContainerWidth();
  const comparing = data2 != null && data2.length > 0;

  const merged = useMemo(() => {
    if (!comparing || data2 == null) return data;
    return mergeTimeSeries(data, data2, "funding_rate", "funding_rate2");
  }, [comparing, data, data2]);

  return (
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && (
        <ComposedChart
          width={width}
          height={height}
          data={merged}
          margin={{ top: 4, right: comparing ? 16 : 72, bottom: 0, left: 8 }}
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
            yAxisId="rate"
            tickFormatter={(v: number) => formatFundingRate(v)}
            stroke={colors.grey}
            tick={{ fill: colors.grey, fontSize: 11 }}
            width={80}
          />
          {!comparing && (
            <YAxis
              yAxisId="premium"
              orientation="right"
              tickFormatter={(v: number) => formatFundingRate(v)}
              stroke={colors.grey}
              tick={{ fill: colors.grey, fontSize: 11 }}
              width={80}
            />
          )}
          <Tooltip
            formatter={(v, name) => [formatFundingRate(v as number), name as string]}
            labelFormatter={(label) => fmtTime(label as number)}
            contentStyle={{
              background: colors.bg,
              border: `1px solid ${colors.grid}`,
              boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
              color: colors.text,
              fontSize: 12,
            }}
          />
          {comparing && (
            <Legend
              formatter={(value) => (
                <span style={{ color: colors.text, fontSize: 12 }}>{value}</span>
              )}
            />
          )}
          <ReferenceLine yAxisId="rate" y={0} stroke={colors.grey} strokeDasharray="3 3" />
          <Bar
            yAxisId="rate"
            dataKey="funding_rate"
            name={label1 ?? "Funding Rate"}
            isAnimationActive={false}
            shape={<FundingBar />}
          />
          {comparing ? (
            <Line
              yAxisId="rate"
              type="monotone"
              dataKey="funding_rate2"
              name={label2 ?? "Compare"}
              stroke={colors.orange}
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              isAnimationActive={false}
            />
          ) : (
            <Line
              yAxisId="premium"
              type="monotone"
              dataKey="premium"
              name="Premium"
              stroke={colors.orange}
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      )}
    </div>
  );
});
