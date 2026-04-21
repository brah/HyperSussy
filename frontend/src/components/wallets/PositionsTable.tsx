import { useMemo } from "react";
import { useWsStore } from "../../api/websocket";
import { CoinLink } from "../common/CoinLink";
import { DataTable, type Column } from "../common/DataTable";
import { EmptyState } from "../common/EmptyState";
import { formatPercent, formatPrice, formatSize, formatUSD } from "../../utils/format";
import { liquidationDistancePct } from "../../utils/position";
import type { PositionItem } from "../../api/types";

interface PositionsTableProps {
  positions: PositionItem[];
}

/** Open positions for a single wallet address, with sortable columns. */
export function PositionsTable({ positions }: Readonly<PositionsTableProps>) {
  const snapshots = useWsStore((s) => s.snapshots);

  // Columns are memoised because some accessors close over `snapshots`.
  const columns = useMemo<Column<PositionItem>[]>(
    () => [
      {
        id: "coin",
        header: "Coin",
        accessor: (p) => p.coin,
        render: (p) => <CoinLink coin={p.coin} />,
      },
      {
        id: "size",
        header: "Size",
        accessor: (p) => Math.abs(p.size),
        render: (p) => formatSize(p.size),
        cellClassName: (p) =>
          `tabular-nums ${p.size >= 0 ? "text-hs-teal" : "text-hs-red"}`,
      },
      {
        id: "notional_usd",
        header: "Notional",
        accessor: (p) => Math.abs(p.notional_usd),
        render: (p) => formatUSD(p.notional_usd),
        cellClassName: "text-hs-text tabular-nums",
      },
      {
        id: "oi_pct",
        header: "OI %",
        accessor: (p) => {
          const snap = snapshots[p.coin];
          return snap && snap.open_interest_usd > 0
            ? Math.abs(p.notional_usd) / snap.open_interest_usd
            : 0;
        },
        render: (p) => {
          const snap = snapshots[p.coin];
          const pct =
            snap && snap.open_interest_usd > 0
              ? (Math.abs(p.notional_usd) / snap.open_interest_usd) * 100
              : null;
          return pct != null ? formatPercent(pct) : "—";
        },
        cellClassName: "text-hs-grey tabular-nums",
      },
      {
        id: "unrealized_pnl",
        header: "Unr. PnL",
        accessor: (p) => p.unrealized_pnl,
        render: (p) => formatUSD(p.unrealized_pnl),
        cellClassName: (p) =>
          `tabular-nums ${p.unrealized_pnl >= 0 ? "text-hs-teal" : "text-hs-red"}`,
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
        accessor: (p) => liquidationDistancePct(p) ?? Infinity,
        render: (p) => {
          if (p.liquidation_price == null) {
            return <span className="text-hs-grey">—</span>;
          }
          const distPct = liquidationDistancePct(p);
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
    ],
    [snapshots],
  );

  if (positions.length === 0) {
    return <EmptyState message="No open positions." />;
  }

  return (
    <DataTable
      columns={columns}
      rows={positions}
      rowKey={(p) => p.coin}
      defaultSortId="notional_usd"
    />
  );
}
