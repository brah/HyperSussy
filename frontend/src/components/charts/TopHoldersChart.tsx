import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { TopHolderItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { formatUSD, shortAddress } from "../../utils/format";

interface TopHoldersChartProps {
  data: TopHolderItem[];
  height?: number;
}

export function TopHoldersChart({ data, height = 260 }: TopHoldersChartProps) {
  const chartData = data.map((d) => ({
    address: shortAddress(d.address, 8),
    volume_usd: d.volume_usd,
    pct:
      d.total_volume > 0
        ? ((d.volume_usd / d.total_volume) * 100).toFixed(1)
        : "0.0",
    fullAddress: d.address,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 16, bottom: 0, left: 72 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} horizontal={false} />
        <XAxis
          type="number"
          tickFormatter={(v: number) => formatUSD(v)}
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="address"
          stroke={colors.grey}
          tick={{ fill: colors.grey, fontSize: 10, fontFamily: "monospace" }}
          width={68}
        />
        <Tooltip
          formatter={(v: number, _name: string, item) => [
            `${formatUSD(v)} (${item.payload.pct}%)`,
            "Volume",
          ]}
          labelFormatter={(addr: string) => addr}
          contentStyle={{
            background: colors.surface,
            border: `1px solid ${colors.grid}`,
            color: colors.text,
            fontSize: 12,
          }}
        />
        <Bar
          dataKey="volume_usd"
          fill={colors.teal}
          isAnimationActive={false}
          radius={[0, 2, 2, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
