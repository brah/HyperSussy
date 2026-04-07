import { memo, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { TopHolderItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { tooltipStyle, fmtPassthroughLabel } from "../../theme/chartDefaults";
import { formatUSD, shortAddress } from "../../utils/format";
import { useContainerWidth } from "../../hooks/useContainerWidth";

interface TopHoldersChartProps {
  data: TopHolderItem[];
  height?: number;
}

// Stable module-level tooltip formatter.
// Item payload carries a `pct` field computed in chartData below.
function fmtHoldersTooltip(
  v: unknown,
  _name: unknown,
  item: { payload?: { pct?: string } },
): [string, string] {
  return [`${formatUSD(v as number)} (${item.payload?.pct ?? "0.0"}%)`, "Volume"];
}

export const TopHoldersChart = memo(function TopHoldersChart({
  data,
  height = 260,
}: Readonly<TopHoldersChartProps>) {
  const [containerRef, width] = useContainerWidth();
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
    <div ref={containerRef} style={{ width: "100%", height }}>
      {width > 0 && (
        <BarChart
          width={width}
          height={height}
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 0, left: 72 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={formatUSD}
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
            formatter={fmtHoldersTooltip}
            labelFormatter={fmtPassthroughLabel}
            contentStyle={tooltipStyle}
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
      )}
    </div>
  );
});
