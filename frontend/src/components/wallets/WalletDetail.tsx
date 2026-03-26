import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  alertsByAddressQuery,
  tradesByAddressQuery,
  whalePositionsQuery,
} from "../../api/queries";
import { AlertFeed } from "../common/AlertFeed";
import { HoursSelector, type Hours } from "../common/HoursSelector";
import { PositionsTable } from "./PositionsTable";
import { TradesTable } from "./TradesTable";
import { shortAddress, formatUSD } from "../../utils/format";

type Tab = "positions" | "trades" | "alerts";

interface WalletDetailProps {
  address: string;
}

/**
 * Embeddable wallet detail panel: summary cards + positions/trades/alerts tabs.
 * Inspired by the Hyperliquid portfolio page layout.
 */
export function WalletDetail({ address }: Readonly<WalletDetailProps>) {
  const [tab, setTab] = useState<Tab>("positions");
  const [hours, setHours] = useState<Hours>(24);

  const { data: positions = [] } = useQuery(whalePositionsQuery(address));
  const { data: trades = [] } = useQuery(tradesByAddressQuery(address, hours));
  const { data: alerts = [] } = useQuery(alertsByAddressQuery(address, 50));

  // Summary metrics derived from positions
  const totalNotional = positions.reduce((s, p) => s + Math.abs(p.notional_usd), 0);
  const totalPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const longNotional = positions
    .filter((p) => p.size > 0)
    .reduce((s, p) => s + p.notional_usd, 0);
  const longPct = totalNotional > 0 ? (longNotional / totalNotional) * 100 : 0;
  const shortPct = 100 - longPct;
  const bias = longPct >= shortPct ? "LONG" : "SHORT";

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "positions", label: "Positions", count: positions.length },
    { id: "trades", label: "Trades", count: trades.length },
    { id: "alerts", label: "Alerts", count: alerts.length },
  ];

  return (
    <div className="flex flex-col gap-4">
      {/* Address header */}
      <div className="flex items-center gap-3">
        <span className="text-hs-text font-semibold">
          {shortAddress(address)}
        </span>
        <span
          className="font-mono text-xs text-hs-grey break-all"
          title={address}
        >
          {address}
        </span>
      </div>

      {/* Summary cards -- inspired by HL portfolio layout */}
      {positions.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="bg-hs-surface border border-hs-grid rounded-lg p-3">
            <p className="text-hs-grey text-xs mb-1">Total Notional</p>
            <p className="text-hs-text font-semibold tabular-nums">
              {formatUSD(totalNotional)}
            </p>
          </div>
          <div className="bg-hs-surface border border-hs-grid rounded-lg p-3">
            <p className="text-hs-grey text-xs mb-1">Direction Bias</p>
            <p
              className={`font-semibold ${
                bias === "LONG" ? "text-hs-green" : "text-hs-red"
              }`}
            >
              {bias}
            </p>
          </div>
          <div className="bg-hs-surface border border-hs-grid rounded-lg p-3">
            <p className="text-hs-grey text-xs mb-1">Position Split</p>
            <div className="flex items-center gap-1 mt-1.5">
              <div
                className="h-1.5 rounded-l bg-hs-green"
                style={{ width: `${longPct}%` }}
              />
              <div
                className="h-1.5 rounded-r bg-hs-red"
                style={{ width: `${shortPct}%` }}
              />
            </div>
            <p className="text-xs text-hs-grey mt-1">
              <span className="text-hs-green">{longPct.toFixed(0)}%</span>
              {" / "}
              <span className="text-hs-red">{shortPct.toFixed(0)}%</span>
            </p>
          </div>
          <div className="bg-hs-surface border border-hs-grid rounded-lg p-3">
            <p className="text-hs-grey text-xs mb-1">Unrealized PnL</p>
            <p
              className={`font-semibold tabular-nums ${
                totalPnl >= 0 ? "text-hs-green" : "text-hs-red"
              }`}
            >
              {totalPnl >= 0 ? "+" : ""}
              {formatUSD(totalPnl)}
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-hs-grid">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? "border-hs-green text-hs-text"
                : "border-transparent text-hs-grey hover:text-hs-text"
            }`}
          >
            {t.label}
            {t.count > 0 && (
              <span className="ml-1.5 text-xs text-hs-grey">({t.count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-hs-surface border border-hs-grid rounded-lg">
        {tab === "positions" && <PositionsTable positions={positions} />}

        {tab === "trades" && (
          <div>
            <div className="flex justify-end p-3 border-b border-hs-grid">
              <HoursSelector value={hours} onChange={setHours} />
            </div>
            <TradesTable trades={trades} hours={hours} />
          </div>
        )}

        {tab === "alerts" && (
          <div className="p-4">
            <AlertFeed alerts={alerts} maxRows={50} />
          </div>
        )}
      </div>
    </div>
  );
}
