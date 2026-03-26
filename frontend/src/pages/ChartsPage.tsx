import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { coinsQuery, fundingQuery, oiQuery } from "../api/queries";
import { CoinSelector } from "../components/common/CoinSelector";
import { FundingChart } from "../components/charts/FundingChart";
import { OIChart } from "../components/charts/OIChart";
import { PageHeader } from "../components/layout/PageHeader";
import { colors } from "../theme/colors";
import { fmtTime } from "../utils/time";
import { formatPrice } from "../utils/format";

const HOUR_OPTIONS = [6, 12, 24, 48, 72] as const;

export function ChartsPage() {
  const [coin, setCoin] = useState("BTC");
  const [hours, setHours] = useState(24);

  const { data: coins = [] } = useQuery(coinsQuery());
  const { data: oiData = [] } = useQuery(oiQuery(coin, hours));
  const { data: fundingData = [] } = useQuery(fundingQuery(coin, hours));

  // Build mark vs oracle from funding data
  const markOracleData = fundingData.map((d) => ({
    timestamp_ms: d.timestamp_ms,
    mark: d.mark_price,
    oracle: d.oracle_price,
  }));

  return (
    <div>
      <PageHeader title="Charts">
        <CoinSelector
          coins={coins}
          value={coin}
          onChange={setCoin}
        />
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="bg-[#141a22] border border-[#2a2d35] text-[#fafafa] text-sm
                     rounded px-3 py-1.5 focus:outline-none focus:border-[#00d4aa]"
        >
          {HOUR_OPTIONS.map((h) => (
            <option key={h} value={h}>
              {h}h
            </option>
          ))}
        </select>
      </PageHeader>

      <div className="space-y-6">
        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
          <h2 className="text-[#fafafa] font-medium mb-3">
            Open Interest — {coin}
          </h2>
          <OIChart data={oiData} />
        </div>

        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
          <h2 className="text-[#fafafa] font-medium mb-3">
            Funding Rate — {coin}
          </h2>
          <FundingChart data={fundingData} />
        </div>

        {markOracleData.length > 0 && (
          <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
            <h2 className="text-[#fafafa] font-medium mb-3">
              Mark vs Oracle Price — {coin}
            </h2>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={markOracleData}
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
                    background: colors.surface,
                    border: `1px solid ${colors.grid}`,
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
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
