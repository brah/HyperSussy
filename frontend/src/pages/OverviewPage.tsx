import { useWsStore } from "../api/websocket";
import { AlertFeed } from "../components/common/AlertFeed";
import { MetricCard } from "../components/common/MetricCard";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusBanner } from "../components/common/StatusBanner";
import { formatPrice, formatUSD, formatFundingRate } from "../utils/format";

export function OverviewPage() {
  const snapshots = useWsStore((s) => s.snapshots);
  const liveAlerts = useWsStore((s) => s.liveAlerts);
  const health = useWsStore((s) => s.health);
  const connected = useWsStore((s) => s.connected);

  const coins = Object.values(snapshots).sort((a, b) =>
    b.open_interest_usd - a.open_interest_usd
  );

  return (
    <div>
      <PageHeader title="Overview">
        <StatusBanner health={health} connected={connected} />
      </PageHeader>

      {coins.length === 0 && (
        <p className="text-[#4a4e69] text-sm mb-6">
          Waiting for live data…
        </p>
      )}

      {/* Market summary table */}
      {coins.length > 0 && (
        <div className="overflow-x-auto mb-8">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2d35] text-[#4a4e69]">
                {["Coin", "Mark Price", "OI (USD)", "Funding Rate", "24h Volume"].map(
                  (h) => (
                    <th key={h} className="py-2 px-3 text-left font-medium">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {coins.map((snap) => (
                <tr
                  key={snap.coin}
                  className="border-b border-[#2a2d35] hover:bg-[#141a22]"
                >
                  <td className="py-2 px-3 text-[#fafafa] font-medium">
                    {snap.coin}
                  </td>
                  <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                    {formatPrice(snap.mark_price)}
                  </td>
                  <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                    {formatUSD(snap.open_interest_usd)}
                  </td>
                  <td
                    className="py-2 px-3 tabular-nums"
                    style={{
                      color: snap.funding_rate >= 0 ? "#00d4aa" : "#ff4b4b",
                    }}
                  >
                    {formatFundingRate(snap.funding_rate)}
                  </td>
                  <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                    {formatUSD(snap.day_volume_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="Assets Tracked"
          value={String(coins.length)}
        />
        <MetricCard
          label="Total OI (USD)"
          value={formatUSD(coins.reduce((s, c) => s + c.open_interest_usd, 0))}
        />
        <MetricCard
          label="24h Volume"
          value={formatUSD(coins.reduce((s, c) => s + c.day_volume_usd, 0))}
        />
        <MetricCard
          label="Live Alerts"
          value={String(liveAlerts.length)}
          valueColor={liveAlerts.length > 0 ? "#ffa500" : undefined}
        />
      </div>

      {/* Recent alerts */}
      <div className="bg-[#141a22] rounded-lg border border-[#2a2d35] p-4">
        <h2 className="text-[#fafafa] font-medium mb-4">Recent Alerts</h2>
        <AlertFeed alerts={liveAlerts} maxRows={20} />
      </div>
    </div>
  );
}
