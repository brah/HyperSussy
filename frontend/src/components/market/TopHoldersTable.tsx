import { useMemo, useState } from "react";
import { useWsStore } from "../../api/websocket";
import { AddressLink } from "../common/AddressLink";
import { formatPrice, formatUSD } from "../../utils/format";
import type { CoinPositionItem } from "../../api/types";

type SortKey =
  | "address"
  | "side"
  | "size"
  | "notional_usd"
  | "oi_pct"
  | "entry_price"
  | "mark_price"
  | "liq_dist_pct"
  | "leverage"
  | "margin_used"
  | "unrealized_pnl";

type SortDir = "asc" | "desc";

interface TopHoldersTableProps {
  coin: string;
  positions: CoinPositionItem[];
}

const HEADERS: { label: string; key: SortKey }[] = [
  { label: "Address", key: "address" },
  { label: "Side", key: "side" },
  { label: "Size", key: "size" },
  { label: "Notional", key: "notional_usd" },
  { label: "OI %", key: "oi_pct" },
  { label: "Entry", key: "entry_price" },
  { label: "Mark", key: "mark_price" },
  { label: "Liq. Price", key: "liq_dist_pct" },
  { label: "Leverage", key: "leverage" },
  { label: "Margin", key: "margin_used" },
  { label: "Unr. PnL", key: "unrealized_pnl" },
];

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
export function TopHoldersTable({
  coin,
  positions,
}: Readonly<TopHoldersTableProps>) {
  const [sortKey, setSortKey] = useState<SortKey>("notional_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const snapshots = useWsStore((s) => s.snapshots);

  const coinOI = snapshots[coin]?.open_interest_usd ?? 0;

  const sorted = useMemo(() => {
    const getValue = (p: CoinPositionItem): number | string => {
      switch (sortKey) {
        case "address":
          return p.address;
        case "side":
          return p.size >= 0 ? "L" : "S";
        case "size":
          return Math.abs(p.size);
        case "notional_usd":
          return Math.abs(p.notional_usd);
        case "oi_pct":
          return coinOI > 0 ? Math.abs(p.notional_usd) / coinOI : 0;
        case "entry_price":
          return p.entry_price ?? 0;
        case "mark_price":
          return p.mark_price;
        case "liq_dist_pct":
          return liqDistPct(p) ?? Infinity;
        case "leverage":
          return p.leverage_value ?? 0;
        case "margin_used":
          return p.margin_used ?? 0;
        case "unrealized_pnl":
          return p.unrealized_pnl;
      }
    };

    return [...positions].sort((a, b) => {
      const av = getValue(a);
      const bv = getValue(b);
      let cmp: number;
      if (typeof av === "string") {
        cmp = av.localeCompare(bv as string);
      } else {
        cmp = av - (bv as number);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [positions, sortKey, sortDir, coinOI]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (positions.length === 0) {
    return (
      <div className="bg-hs-surface border border-hs-grid rounded-lg p-4">
        <h2 className="text-hs-text font-medium mb-3">Top Positions — {coin}</h2>
        <p className="text-hs-grey text-sm py-6 text-center">No open positions tracked.</p>
      </div>
    );
  }

  return (
    <div className="bg-hs-surface border border-hs-grid rounded-lg p-4">
      <h2 className="text-hs-text font-medium mb-3">Top Positions — {coin}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hs-grid text-hs-grey">
              {HEADERS.map(({ label, key }) => (
                <th
                  key={key}
                  className="py-2 px-3 text-left font-medium cursor-pointer select-none hover:text-hs-text whitespace-nowrap"
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
              const isLong = p.size >= 0;
              const oiPct =
                coinOI > 0
                  ? (Math.abs(p.notional_usd) / coinOI) * 100
                  : null;
              const distPct = liqDistPct(p);

              return (
                <tr
                  key={p.address}
                  className="border-b border-hs-grid hover:bg-hs-bg"
                >
                  <td className="py-2 px-3">
                    <AddressLink address={p.address} />
                  </td>
                  <td
                    className={`py-2 px-3 font-medium ${isLong ? "text-hs-green" : "text-hs-red"}`}
                  >
                    {isLong ? "L" : "S"}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {Math.abs(p.size).toFixed(4)}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {formatUSD(Math.abs(p.notional_usd))}
                  </td>
                  <td className="py-2 px-3 text-hs-grey tabular-nums">
                    {oiPct == null ? "—" : `${oiPct.toFixed(2)}%`}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {p.entry_price == null ? "—" : formatPrice(p.entry_price)}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {formatPrice(p.mark_price)}
                  </td>
                  <td className="py-2 px-3 tabular-nums">
                    {p.liquidation_price == null ? (
                      <span className="text-hs-grey">—</span>
                    ) : (
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
                    )}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {formatLeverage(p.leverage_value, p.leverage_type)}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {p.margin_used == null ? "—" : formatUSD(p.margin_used)}
                  </td>
                  <td
                    className={`py-2 px-3 tabular-nums ${
                      p.unrealized_pnl >= 0 ? "text-hs-green" : "text-hs-red"
                    }`}
                  >
                    {formatUSD(p.unrealized_pnl)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
