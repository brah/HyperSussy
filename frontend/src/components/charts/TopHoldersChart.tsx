import { memo, useMemo } from "react";
import { useNavigate } from "react-router-dom";
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

export const TopHoldersChart = memo(function TopHoldersChart({
  data,
  height = 260,
}: Readonly<TopHoldersChartProps>) {
  const navigate = useNavigate();
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        address: shortAddress(d.address, 4),
        volume_usd: d.volume_usd,
        pct:
          d.total_volume > 0
            ? ((d.volume_usd / d.total_volume) * 100).toFixed(1)
            : "0.0",
        fullAddress: d.address,
      })),
    [data]
  );

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
            background: colors.bg,
            border: `1px solid ${colors.grid}`,
            boxShadow: "rgba(14,15,12,0.12) 0px 0px 0px 1px",
            color: colors.text,
            fontSize: 12,
          }}
        />
        <Bar
          dataKey="volume_usd"
          fill={colors.teal}
          isAnimationActive={false}
          radius={[0, 2, 2, 0]}
          cursor="pointer"
          onClick={(barPayload) => {
            const addr = (barPayload as { payload?: { fullAddress?: string } })
              .payload?.fullAddress;
            if (addr) navigate(`/wallets/${addr}`);
          }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
});
