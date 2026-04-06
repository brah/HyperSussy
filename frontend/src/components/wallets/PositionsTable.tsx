import { useMemo, useState } from "react";
import { useWsStore } from "../../api/websocket";
import { EmptyState } from "../common/EmptyState";
import { formatPrice, formatUSD } from "../../utils/format";
import type { PositionItem } from "../../api/types";

type SortKey =
  | "coin"
  | "size"
  | "notional_usd"
  | "oi_pct"
  | "unrealized_pnl"
  | "mark_price"
  | "liq_dist_pct";
type SortDir = "asc" | "desc";

interface PositionsTableProps {
  positions: PositionItem[];
}

const HEADERS: { label: string; key: SortKey }[] = [
  { label: "Coin", key: "coin" },
  { label: "Size", key: "size" },
  { label: "Notional", key: "notional_usd" },
  { label: "OI %", key: "oi_pct" },
  { label: "Unr. PnL", key: "unrealized_pnl" },
  { label: "Mark", key: "mark_price" },
  { label: "Liq. Price", key: "liq_dist_pct" },
];

function liqDistPct(p: PositionItem): number | null {
  if (p.liquidation_price == null || p.mark_price === 0) return null;
  return (Math.abs(p.mark_price - p.liquidation_price) / p.mark_price) * 100;
}

/** Open positions for a single wallet address, with sortable columns. */
export function PositionsTable({ positions }: Readonly<PositionsTableProps>) {
  const [sortKey, setSortKey] = useState<SortKey>("notional_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const snapshots = useWsStore((s) => s.snapshots);

  const sorted = useMemo(() => {
    const getValue = (p: PositionItem): number | string => {
      switch (sortKey) {
        case "coin":
          return p.coin;
        case "size":
          return Math.abs(p.size);
        case "notional_usd":
          return Math.abs(p.notional_usd);
        case "oi_pct": {
          const snap = snapshots[p.coin];
          return snap && snap.open_interest_usd > 0
            ? Math.abs(p.notional_usd) / snap.open_interest_usd
            : 0;
        }
        case "unrealized_pnl":
          return p.unrealized_pnl;
        case "mark_price":
          return p.mark_price;
        case "liq_dist_pct":
          return liqDistPct(p) ?? Infinity;
      }
    };

    return [...positions].sort((a, b) => {
      const av = getValue(a);
      const bv = getValue(b);
      const cmp =
        typeof av === "string"
          ? av.localeCompare(bv as string)
          : (av as number) - (bv as number);
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [positions, sortKey, sortDir, snapshots]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (positions.length === 0) {
    return <EmptyState message="No open positions." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
            {HEADERS.map(({ label, key }) => (
              <th
                key={key}
                className="py-2 px-3 text-left font-medium cursor-pointer select-none hover:text-hs-text"
                onClick={() => handleSort(key)}
              >
                {label}
                {sortKey === key && (
                  <span className="ml-1 text-xs">
                    {sortDir === "asc" ? "↑" : "↓"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => {
            const snap = snapshots[p.coin];
            const oiPct =
              snap && snap.open_interest_usd > 0
                ? (Math.abs(p.notional_usd) / snap.open_interest_usd) * 100
                : null;
            const distPct = liqDistPct(p);

            return (
              <tr
                key={p.coin}
                className="border-b border-hs-grid hover:bg-hs-mint/50"
              >
                <td className="py-2 px-3 text-hs-text font-medium">{p.coin}</td>
                <td
                  className={`py-2 px-3 tabular-nums ${
                    p.size >= 0 ? "text-hs-teal" : "text-hs-red"
                  }`}
                >
                  {p.size.toFixed(4)}
                </td>
                <td className="py-2 px-3 text-hs-text tabular-nums">
                  {formatUSD(p.notional_usd)}
                </td>
                <td className="py-2 px-3 text-hs-grey tabular-nums">
                  {oiPct != null ? `${oiPct.toFixed(2)}%` : "—"}
                </td>
                <td
                  className={`py-2 px-3 tabular-nums ${
                    p.unrealized_pnl >= 0 ? "text-hs-teal" : "text-hs-red"
                  }`}
                >
                  {formatUSD(p.unrealized_pnl)}
                </td>
                <td className="py-2 px-3 text-hs-text tabular-nums">
                  {formatPrice(p.mark_price)}
                </td>
                <td className="py-2 px-3 tabular-nums">
                  {p.liquidation_price != null ? (
                    <>
                      <span className="text-hs-text">
                        {formatPrice(p.liquidation_price)}
                      </span>
                      {distPct != null && (
                        <span className="ml-1 text-xs text-hs-orange">
                          ({distPct.toFixed(1)}%)
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-hs-grey">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
