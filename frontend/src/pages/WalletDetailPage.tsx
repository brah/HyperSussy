import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  alertsByAddressQuery,
  tradesByAddressQuery,
  whalePositionsQuery,
} from "../api/queries";
import { AlertFeed } from "../components/common/AlertFeed";
import { PageHeader } from "../components/layout/PageHeader";
import { EmptyState } from "../components/common/EmptyState";
import { shortAddress, formatPrice, formatUSD } from "../utils/format";
import { fmtDatetime } from "../utils/time";

type Tab = "positions" | "trades" | "alerts";

export function WalletDetailPage() {
  const { address = "" } = useParams<{ address: string }>();
  const [tab, setTab] = useState<Tab>("positions");
  const [hours, setHours] = useState(24);

  const { data: positions = [] } = useQuery(whalePositionsQuery(address));
  const { data: trades = [] } = useQuery(
    tradesByAddressQuery(address, hours)
  );
  const { data: alerts = [] } = useQuery(alertsByAddressQuery(address, 50));

  const label = shortAddress(address);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "positions", label: "Positions", count: positions.length },
    { id: "trades", label: "Trades", count: trades.length },
    { id: "alerts", label: "Alerts", count: alerts.length },
  ];

  return (
    <div>
      <PageHeader title={`Wallet ${label}`}>
        <span
          className="font-mono text-xs text-[#4a4e69] break-all max-w-xs"
          title={address}
        >
          {address}
        </span>
      </PageHeader>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-[#2a2d35]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? "border-[#00d4aa] text-[#fafafa]"
                : "border-transparent text-[#4a4e69] hover:text-[#fafafa]"
            }`}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="ml-1.5 text-xs text-[#4a4e69]">
                ({t.count})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Positions */}
      {tab === "positions" && (
        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg">
          {positions.length === 0 ? (
            <EmptyState message="No open positions." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2a2d35] text-[#4a4e69]">
                    {["Coin", "Size", "Notional", "Unr. PnL", "Mark", "Liq. Price"].map(
                      (h) => (
                        <th key={h} className="py-2 px-3 text-left font-medium">
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr
                      key={p.coin}
                      className="border-b border-[#2a2d35] hover:bg-[#0e1117]"
                    >
                      <td className="py-2 px-3 text-[#fafafa] font-medium">
                        {p.coin}
                      </td>
                      <td
                        className="py-2 px-3 tabular-nums"
                        style={{ color: p.size >= 0 ? "#00d4aa" : "#ff4b4b" }}
                      >
                        {p.size.toFixed(4)}
                      </td>
                      <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                        {formatUSD(p.notional_usd)}
                      </td>
                      <td
                        className="py-2 px-3 tabular-nums"
                        style={{
                          color: p.unrealized_pnl >= 0 ? "#00d4aa" : "#ff4b4b",
                        }}
                      >
                        {formatUSD(p.unrealized_pnl)}
                      </td>
                      <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                        {formatPrice(p.mark_price)}
                      </td>
                      <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                        {p.liquidation_price != null
                          ? formatPrice(p.liquidation_price)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Trades */}
      {tab === "trades" && (
        <div>
          <div className="flex justify-end mb-3">
            <select
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="bg-[#141a22] border border-[#2a2d35] text-[#fafafa] text-sm
                         rounded px-3 py-1.5 focus:outline-none focus:border-[#00d4aa]"
            >
              {[6, 12, 24, 48, 72].map((h) => (
                <option key={h} value={h}>
                  {h}h
                </option>
              ))}
            </select>
          </div>
          <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg">
            {trades.length === 0 ? (
              <EmptyState message={`No trades in the last ${hours}h.`} />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2a2d35] text-[#4a4e69]">
                      {["Time", "Coin", "Side", "Price", "Size", "Volume"].map(
                        (h) => (
                          <th
                            key={h}
                            className="py-2 px-3 text-left font-medium"
                          >
                            {h}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t) => (
                      <tr
                        key={t.tid}
                        className="border-b border-[#2a2d35] hover:bg-[#0e1117]"
                      >
                        <td className="py-2 px-3 text-[#4a4e69] text-xs">
                          {fmtDatetime(t.timestamp_ms)}
                        </td>
                        <td className="py-2 px-3 text-[#fafafa]">{t.coin}</td>
                        <td
                          className="py-2 px-3 font-medium"
                          style={{
                            color: t.side === "B" ? "#00d4aa" : "#ff4b4b",
                          }}
                        >
                          {t.side === "B" ? "Buy" : "Sell"}
                        </td>
                        <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                          {formatPrice(t.price)}
                        </td>
                        <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                          {t.size.toFixed(4)}
                        </td>
                        <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                          {formatUSD(t.price * t.size)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Alerts */}
      {tab === "alerts" && (
        <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4">
          <AlertFeed alerts={alerts} maxRows={50} />
        </div>
      )}
    </div>
  );
}
