import { memo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { OISnapshotItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { fmtTime } from "../../utils/time";
import { formatUSD } from "../../utils/format";

interface OIChartProps {
  data: OISnapshotItem[];
  height?: number;
}

export const OIChart = memo(function OIChart({ data, height = 260 }: Readonly<OIChartProps>) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
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
          tickFormatter={(v: number) => formatUSD(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
          width={72}
        />
        <Tooltip
          formatter={(v: number) => [formatUSD(v), "OI (USD)"]}
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
          type="monotone"
          dataKey="open_interest_usd"
          stroke={colors.teal}
          fill="url(#oi-grad)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
});
