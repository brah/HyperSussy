import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  alertsByAddressQuery,
  realizedPnlQuery,
  whalePositionsQuery,
} from "../../api/queries";
import { usePanelVisible } from "../../stores/panelStore";
import { AlertFeed } from "../common/AlertFeed";
import { EmptyState } from "../common/EmptyState";
import { FillHistoryTable } from "./FillHistoryTable";
import { PositionsTable } from "./PositionsTable";
import { shortAddress, formatUSD } from "../../utils/format";

type Tab = "positions" | "fills" | "alerts";

interface WalletDetailProps {
  address: string;
}

/**
 * Embeddable wallet detail panel: summary cards + positions/fills/alerts tabs.
 * Inspired by the Hyperliquid portfolio page layout.
 */
export function WalletDetail({ address }: Readonly<WalletDetailProps>) {
  const [tab, setTab] = useState<Tab>("positions");
  const showPositions = usePanelVisible("wallet-positions");
  const showFills = usePanelVisible("wallet-fills");
  const showAlerts = usePanelVisible("wallet-alerts");

  const { data: positions = [] } = useQuery({
    ...whalePositionsQuery(address),
    enabled: showPositions && address.length === 42,
  });
  const { data: alerts = [] } = useQuery({
    ...alertsByAddressQuery(address, 50),
    enabled: showAlerts && address.length === 42,
  });
  const { data: pnlData } = useQuery({
    ...realizedPnlQuery(address),
    enabled: address.length === 42,
  });

  // Summary metrics derived from positions
  const totalNotional = positions.reduce((s, p) => s + Math.abs(p.notional_usd), 0);
  const totalPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const longNotional = positions
    .filter((p) => p.size > 0)
    .reduce((s, p) => s + p.notional_usd, 0);
  const longPct = totalNotional > 0 ? (longNotional / totalNotional) * 100 : 0;
  const shortPct = 100 - longPct;
  const bias = longPct >= shortPct ? "LONG" : "SHORT";

  const tabs = useMemo(() => {
    const all: { id: Tab; label: string; count: number }[] = [
      { id: "positions", label: "Positions", count: positions.length },
      { id: "fills", label: "Fills", count: 0 },
      { id: "alerts", label: "Alerts", count: alerts.length },
    ];
    return all.filter(({ id }) => {
      if (id === "positions") return showPositions;
      if (id === "fills") return showFills;
      return showAlerts;
    });
  }, [positions.length, alerts.length, showPositions, showFills, showAlerts]);

  useEffect(() => {
    if (tabs.length === 0) {
      return;
    }
    if (!tabs.some((item) => item.id === tab)) {
      setTab(tabs[0].id);
    }
  }, [tab, tabs]);

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

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {positions.length > 0 && (
          <>
            <div className="bg-hs-surface border border-hs-grid rounded-2xl p-3">
              <p className="text-hs-grey text-xs mb-1">Total Notional</p>
              <p className="text-hs-text font-semibold tabular-nums">
                {formatUSD(totalNotional)}
              </p>
            </div>
            <div className="bg-hs-surface border border-hs-grid rounded-2xl p-3">
              <p className="text-hs-grey text-xs mb-1">Direction Bias</p>
              <div className="flex items-center gap-2">
                <p
                  className={`font-semibold ${
                    bias === "LONG" ? "text-hs-teal" : "text-hs-red"
                  }`}
                >
                  {bias}
                </p>
                <span className="text-xs text-hs-grey">
                  <span className="text-hs-teal">{longPct.toFixed(0)}%</span>
                  {" / "}
                  <span className="text-hs-red">{shortPct.toFixed(0)}%</span>
                </span>
              </div>
            </div>
            <div className="bg-hs-surface border border-hs-grid rounded-2xl p-3">
              <p className="text-hs-grey text-xs mb-1">Unrealized PnL</p>
              <p
                className={`font-semibold tabular-nums ${
                  totalPnl >= 0 ? "text-hs-teal" : "text-hs-red"
                }`}
              >
                {totalPnl >= 0 ? "+" : ""}
                {formatUSD(totalPnl)}
              </p>
            </div>
          </>
        )}
        {pnlData != null && (
          <>
            <div className="bg-hs-surface border border-hs-grid rounded-2xl p-3">
              <p className="text-hs-grey text-xs mb-1">Realized PnL (7d)</p>
              <p
                className={`font-semibold tabular-nums ${
                  pnlData.pnl_7d >= 0 ? "text-hs-teal" : "text-hs-red"
                }`}
              >
                {pnlData.pnl_7d >= 0 ? "+" : ""}
                {formatUSD(pnlData.pnl_7d)}
              </p>
              <p className="text-xs text-hs-grey mt-0.5">
                {pnlData.is_complete_7d ? "" : "~"}
                {pnlData.fills_7d.toLocaleString()} fill{pnlData.fills_7d !== 1 ? "s" : ""}
                {pnlData.is_complete_7d ? "" : "+"}
              </p>
            </div>
            <div className="bg-hs-surface border border-hs-grid rounded-2xl p-3">
              <p className="text-hs-grey text-xs mb-1">
                Realized PnL (All){pnlData.is_complete_all_time ? "" : "*"}
              </p>
              <p
                className={`font-semibold tabular-nums ${
                  pnlData.pnl_all_time >= 0 ? "text-hs-teal" : "text-hs-red"
                }`}
              >
                {pnlData.pnl_all_time >= 0 ? "+" : ""}
                {formatUSD(pnlData.pnl_all_time)}
              </p>
              <p className="text-xs text-hs-grey mt-0.5">
                {pnlData.is_complete_all_time ? "" : "~"}
                {pnlData.fills_all_time.toLocaleString()} fill{pnlData.fills_all_time !== 1 ? "s" : ""}
                {pnlData.is_complete_all_time ? "" : "+"}
              </p>
            </div>
          </>
        )}
      </div>

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
      <div className="bg-hs-surface border border-hs-grid rounded-2xl">
        {tabs.length === 0 ? (
          <EmptyState message="Enable at least one wallet panel above." />
        ) : (
          <>
            {tab === "positions" && <PositionsTable positions={positions} />}
            {tab === "fills" && <FillHistoryTable address={address} />}
            {tab === "alerts" && (
              <div className="p-4">
                <AlertFeed alerts={alerts} maxRows={50} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
