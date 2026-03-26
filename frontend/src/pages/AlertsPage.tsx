import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { alertCountsQuery, alertsQuery } from "../api/queries";
import { AlertFeed } from "../components/common/AlertFeed";
import { PageHeader } from "../components/layout/PageHeader";
import { colors } from "../theme/colors";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"];

export function AlertsPage() {
  const [limit, setLimit] = useState(200);

  const { data: alerts = [] } = useQuery(alertsQuery(limit, 0));
  const { data: counts = {} } = useQuery(alertCountsQuery(0));

  const countData = Object.entries(counts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);

  const severityCounts = Object.fromEntries(
    SEVERITY_ORDER.map((sev) => [
      sev,
      alerts.filter((a) => a.severity === sev).length,
    ])
  );

  return (
    <div>
      <PageHeader title="Alerts">
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="bg-[#141a22] border border-[#2a2d35] text-[#fafafa] text-sm
                     rounded px-3 py-1.5 focus:outline-none focus:border-[#00d4aa]"
        >
          {[50, 100, 200, 500].map((n) => (
            <option key={n} value={n}>
              Last {n}
            </option>
          ))}
        </select>
      </PageHeader>

      {/* Severity pill counts */}
      <div className="flex gap-3 mb-6">
        {SEVERITY_ORDER.map((sev) => (
          <div
            key={sev}
            className="flex items-center gap-2 bg-[#141a22] border border-[#2a2d35]
                       rounded px-3 py-1.5"
          >
            <span
              className="capitalize text-sm font-medium"
              style={{ color: sev === "critical" ? colors.red : sev === "high" ? colors.orange : sev === "medium" ? "#f59e0b" : colors.grey }}
            >
              {sev}
            </span>
            <span className="text-[#fafafa] text-sm font-semibold">
              {severityCounts[sev] ?? 0}
            </span>
          </div>
        ))}
      </div>

      {/* Alerts by type bar chart */}
      {countData.length > 0 && (
        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4 mb-6">
          <h2 className="text-[#fafafa] font-medium mb-3">Alerts by Engine</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={countData}
              layout="vertical"
              margin={{ top: 0, right: 16, bottom: 0, left: 120 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} horizontal={false} />
              <XAxis type="number" stroke={colors.grey} tick={{ fill: colors.grey, fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="type"
                stroke={colors.grey}
                tick={{ fill: colors.grey, fontSize: 11 }}
                width={116}
              />
              <Tooltip
                contentStyle={{
                  background: colors.surface,
                  border: `1px solid ${colors.grid}`,
                  color: colors.text,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" fill={colors.teal} isAnimationActive={false} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Alert feed */}
      <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
        <h2 className="text-[#fafafa] font-medium mb-3">
          Recent Alerts ({alerts.length})
        </h2>
        <AlertFeed alerts={alerts} maxRows={limit} />
      </div>
    </div>
  );
}
