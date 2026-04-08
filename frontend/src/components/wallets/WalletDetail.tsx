import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  alertsByAddressQuery,
  realizedPnlQuery,
  walletAccountQuery,
  whalePositionsQuery,
} from "../../api/queries";
import { usePanelVisible } from "../../stores/panelStore";
import { AlertFeed } from "../common/AlertFeed";
import { EmptyState } from "../common/EmptyState";
import { MetricCard } from "../common/MetricCard";
import { WatchStar } from "../common/WatchStar";
import { FillHistoryTable } from "./FillHistoryTable";
import { PositionsTable } from "./PositionsTable";
import { SpotAssetsTable } from "./SpotAssetsTable";
import { shortAddress, formatPercent, formatUSD } from "../../utils/format";

type Tab = "positions" | "fills" | "alerts" | "spot";

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
  const { data: accountData } = useQuery({
    ...walletAccountQuery(address),
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
      { id: "spot", label: "Spot Assets", count: accountData?.spot.length ?? 0 },
    ];
    return all.filter(({ id }) => {
      if (id === "positions") return showPositions;
      if (id === "fills") return showFills;
      if (id === "alerts") return showAlerts;
      return true; // spot always visible
    });
  }, [positions.length, alerts.length, accountData?.spot.length, showPositions, showFills, showAlerts]);

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
        <WatchStar kind="wallet" id={address} label={shortAddress(address)} />
        <span
          className="font-mono text-xs text-hs-grey break-all"
          title={address}
        >
          {address}
        </span>
      </div>

      {/* Account equity summary */}
      {accountData != null && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            compact
            label="Account Value"
            value={formatUSD(accountData.account_value)}
            valueClassName="text-hs-text tabular-nums"
          />
          <MetricCard
            compact
            label="Withdrawable"
            value={formatUSD(accountData.withdrawable)}
            valueClassName="text-hs-teal tabular-nums"
          />
          <MetricCard
            compact
            label="Margin Used"
            value={formatUSD(accountData.total_margin_used)}
            valueClassName="text-hs-text tabular-nums"
          />
          <MetricCard
            compact
            label="Position Value"
            value={formatUSD(accountData.total_ntl_pos)}
            valueClassName="text-hs-text tabular-nums"
          />
        </div>
      )}

      {/* Position-derived summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {positions.length > 0 && (
          <>
            <MetricCard
              compact
              label="Total Notional"
              value={formatUSD(totalNotional)}
              valueClassName="text-hs-text tabular-nums"
            />
            <MetricCard
              compact
              label="Direction Bias"
              valueNode={
                <div className="flex items-center gap-2">
                  <p
                    className={`font-semibold ${
                      bias === "LONG" ? "text-hs-teal" : "text-hs-red"
                    }`}
                  >
                    {bias}
                  </p>
                  <span className="text-xs text-hs-grey">
                    <span className="text-hs-teal">{formatPercent(longPct, 0)}</span>
                    {" / "}
                    <span className="text-hs-red">{formatPercent(shortPct, 0)}</span>
                  </span>
                </div>
              }
            />
            <MetricCard
              compact
              label="Unrealized PnL"
              value={`${totalPnl >= 0 ? "+" : ""}${formatUSD(totalPnl)}`}
              valueClassName={`tabular-nums ${
                totalPnl >= 0 ? "text-hs-teal" : "text-hs-red"
              }`}
            />
          </>
        )}
        {pnlData != null && (
          <>
            <MetricCard
              compact
              label="Realized PnL (7d)"
              value={`${pnlData.pnl_7d >= 0 ? "+" : ""}${formatUSD(pnlData.pnl_7d)}`}
              valueClassName={`tabular-nums ${
                pnlData.pnl_7d >= 0 ? "text-hs-teal" : "text-hs-red"
              }`}
              sub={`${pnlData.is_complete_7d ? "" : "~"}${pnlData.fills_7d.toLocaleString()} fill${
                pnlData.fills_7d !== 1 ? "s" : ""
              }${pnlData.is_complete_7d ? "" : "+"}`}
            />
            <MetricCard
              compact
              label={`Realized PnL (All)${pnlData.is_complete_all_time ? "" : "*"}`}
              value={`${pnlData.pnl_all_time >= 0 ? "+" : ""}${formatUSD(pnlData.pnl_all_time)}`}
              valueClassName={`tabular-nums ${
                pnlData.pnl_all_time >= 0 ? "text-hs-teal" : "text-hs-red"
              }`}
              sub={`${pnlData.is_complete_all_time ? "" : "~"}${pnlData.fills_all_time.toLocaleString()} fill${
                pnlData.fills_all_time !== 1 ? "s" : ""
              }${pnlData.is_complete_all_time ? "" : "+"}`}
            />
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
            {tab === "spot" && (
              <SpotAssetsTable assets={accountData?.spot ?? []} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
