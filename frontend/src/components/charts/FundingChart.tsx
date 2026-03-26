import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { FundingSnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatFundingRate } from "../../utils/format";

interface FundingChartProps {
  data: FundingSnapshotItem[];
  height?: number;
}

export function FundingChart({ data, height = 220 }: FundingChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
        <XAxis
          dataKey="timestamp_ms"
          tickFormatter={(v: number) => fmtTime(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
          minTickGap={60}
        />
        <YAxis
          tickFormatter={(v: number) => formatFundingRate(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
          width={80}
        />
        <Tooltip
          formatter={(v: number) => [formatFundingRate(v), "Funding Rate"]}
          labelFormatter={(ms: number) => fmtTime(ms)}
          contentStyle={{
            background: colors.surface,
            border: `1px solid ${colors.grid}`,
            color: colors.text,
            fontSize: 12,
          }}
        />
        <ReferenceLine y={0} stroke={colors.grey} strokeDasharray="3 3" />
        <Bar dataKey="funding_rate" isAnimationActive={false}>
          {data.map((entry, idx) => (
            <Cell
              key={idx}
              fill={entry.funding_rate >= 0 ? colors.teal : colors.red}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
