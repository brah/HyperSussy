import { memo, useMemo } from "react";
import { useWsStore } from "../../api/websocket";
import { AddressLink } from "../common/AddressLink";
import { DataTable, type Column } from "../common/DataTable";
import { EmptyState } from "../common/EmptyState";
import { PanelCard } from "../common/PanelCard";
import { formatPercent, formatPrice, formatSize, formatUSD } from "../../utils/format";
import type { CoinPositionItem } from "../../api/types";

interface TopHoldersTableProps {
  coin: string;
  positions: CoinPositionItem[];
}

function liqDistPct(p: CoinPositionItem): number | null {
  if (p.liquidation_price == null || p.mark_price === 0) return null;
  return (Math.abs(p.mark_price - p.liquidation_price) / p.mark_price) * 100;
}

function formatLeverage(value: number | null, type: string | null): string {
  if (value == null) return "—";
  const base = `${value.toFixed(1)}x`;
  return type == null ? base : `${base} ${type}`;
}

/** Top open positions across all tracked wallets for a given coin. */
export const TopHoldersTable = memo(function TopHoldersTable({
  coin,
  positions,
}: Readonly<TopHoldersTableProps>) {
  // Subscribe to the single value needed rather than the whole snapshots dict.
  // The dict reference changes on every WS flush (2/sec); subscribing broadly
  // would cause a full DataTable re-render on every push.
  const coinOI = useWsStore((s) => s.snapshots[coin]?.open_interest_usd ?? 0);

  const columns = useMemo<Column<CoinPositionItem>[]>(
    () => [
      {
        id: "address",
        header: "Address",
        accessor: (p) => p.address,
        render: (p) => <AddressLink address={p.address} />,
      },
      {
        id: "side",
        header: "Side",
        accessor: (p) => (p.size >= 0 ? "L" : "S"),
        render: (p) => (p.size >= 0 ? "L" : "S"),
        cellClassName: (p) =>
          `font-medium ${p.size >= 0 ? "text-hs-teal" : "text-hs-red"}`,
      },
      {
        id: "size",
        header: "Size",
        accessor: (p) => Math.abs(p.size),
        render: (p) => formatSize(Math.abs(p.size)),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "notional_usd",
        header: "Notional",
        accessor: (p) => Math.abs(p.notional_usd),
        render: (p) => formatUSD(Math.abs(p.notional_usd)),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "oi_pct",
        header: "OI %",
        accessor: (p) => (coinOI > 0 ? Math.abs(p.notional_usd) / coinOI : 0),
        render: (p) => {
          const pct =
            coinOI > 0 ? (Math.abs(p.notional_usd) / coinOI) * 100 : null;
          return pct == null ? "—" : formatPercent(pct);
        },
        cellClassName: "text-hs-grey tabular-nums",
      },
      {
        id: "entry_price",
        header: "Entry",
        accessor: (p) => p.entry_price ?? 0,
        render: (p) => (p.entry_price == null ? "—" : formatPrice(p.entry_price)),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "mark_price",
        header: "Mark",
        accessor: (p) => p.mark_price,
        render: (p) => formatPrice(p.mark_price),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "liq_dist_pct",
        header: "Liq. Price",
        accessor: (p) => liqDistPct(p) ?? Infinity,
        render: (p) => {
          if (p.liquidation_price == null) {
            return <span className="text-hs-grey">—</span>;
          }
          const distPct = liqDistPct(p);
          return (
            <>
              <span className="text-hs-text">
                {formatPrice(p.liquidation_price)}
              </span>
              {distPct != null && (
                <span className="ml-1 text-xs text-hs-orange">
                  ({formatPercent(distPct, 1)})
                </span>
              )}
            </>
          );
        },
        cellClassName: "tabular-nums",
      },
      {
        id: "leverage",
        header: "Leverage",
        accessor: (p) => p.leverage_value ?? 0,
        render: (p) => formatLeverage(p.leverage_value, p.leverage_type),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "margin_used",
        header: "Margin",
        accessor: (p) => p.margin_used ?? 0,
        render: (p) => (p.margin_used == null ? "—" : formatUSD(p.margin_used)),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "unrealized_pnl",
        header: "Unr. PnL",
        accessor: (p) => p.unrealized_pnl,
        render: (p) => formatUSD(p.unrealized_pnl),
        cellClassName: (p) =>
          `tabular-nums ${
            p.unrealized_pnl >= 0 ? "text-hs-teal" : "text-hs-red"
          }`,
      },
    ],
    [coinOI],
  );

  return (
    <PanelCard title={`Top Positions — ${coin}`}>
      {positions.length === 0 ? (
        <EmptyState message="No open positions tracked." compact />
      ) : (
        <DataTable
          columns={columns}
          rows={positions}
          rowKey={(p) => p.address}
          defaultSortId="notional_usd"
        />
      )}
    </PanelCard>
  );
});
