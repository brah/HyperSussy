import { memo, useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { TradeFlowItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatUSD } from "../../utils/format";

interface TradeFlowChartProps {
  data: TradeFlowItem[];
  height?: number;
}

interface BucketRow {
  bucket: number;
  buy: number;
  sell: number;
}

function pivotFlow(data: TradeFlowItem[]): BucketRow[] {
  const byBucket = new Map<number, BucketRow>();
  for (const row of data) {
    const existing = byBucket.get(row.bucket) ?? { bucket: row.bucket, buy: 0, sell: 0 };
    if (row.side === "B") existing.buy += row.volume_usd;
    else existing.sell += row.volume_usd;
    byBucket.set(row.bucket, existing);
  }
  return [...byBucket.values()].sort((a, b) => a.bucket - b.bucket);
}

export const TradeFlowChart = memo(function TradeFlowChart({
  data,
  height = 220,
}: Readonly<TradeFlowChartProps>) {
  const pivoted = useMemo(() => pivotFlow(data), [data]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={pivoted}
        margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
        <XAxis
          dataKey="bucket"
          tickFormatter={(v: number) => fmtTime(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
          minTickGap={60}
        />
        <YAxis
          tickFormatter={(v: number) => formatUSD(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
          width={72}
        />
        <Tooltip
          formatter={(v: number, name: string) => [
            formatUSD(v),
            name === "buy" ? "Buy Volume" : "Sell Volume",
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
          formatter={(value: string) =>
            value === "buy" ? "Buy" : "Sell"
          }
        />
        <Bar dataKey="buy" fill={colors.teal} isAnimationActive={false} />
        <Bar dataKey="sell" fill={colors.red} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
});
