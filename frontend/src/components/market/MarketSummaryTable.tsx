import { useMemo, useState } from "react";
import { useWsStore } from "../../api/websocket";
import { formatPrice, formatUSD, formatFundingRate } from "../../utils/format";
import type { LiveSnapshot } from "../../api/types";

type SortKey = "coin" | "mark_price" | "open_interest_usd" | "funding_rate" | "day_volume_usd";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "coin", label: "Coin" },
  { key: "mark_price", label: "Mark Price" },
  { key: "open_interest_usd", label: "OI (USD)" },
  { key: "funding_rate", label: "Funding Rate" },
  { key: "day_volume_usd", label: "24h Volume" },
];

interface MarketSummaryTableProps {
  onSelectCoin: (coin: string) => void;
}

/**
 * Full-market table sourced from live WebSocket snapshots.
 * Clicking a row selects the coin for analytics view.
 */
export function MarketSummaryTable({
  onSelectCoin,
}: Readonly<MarketSummaryTableProps>) {
  const snapshots = useWsStore((s) => s.snapshots);
  const [sortKey, setSortKey] = useState<SortKey>("open_interest_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const coins = useMemo(() => {
    const list = Object.values(snapshots).filter(
      (s) => s.open_interest_usd > 0 || s.day_volume_usd > 0,
    );
    return list.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      let cmp: number;
      if (typeof av === "string" && typeof bv === "string") {
        cmp = av.localeCompare(bv);
      } else {
        cmp = Number(av) - Number(bv);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [snapshots, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "coin" ? "asc" : "desc");
    }
  }

  if (coins.length === 0) {
    // Render a skeleton table that approximates the loaded layout.
    // This prevents a CLS when live data arrives and the table expands from
    // an empty-state placeholder to its full height.
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hs-grid text-hs-grey">
              {COLUMNS.map(({ key, label }) => (
                <th key={key} className="py-2 px-3 text-left font-medium">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 20 }, (_, i) => `skeleton-${i}`).map((key) => (
              <tr key={key} className="border-b border-hs-grid">
                {COLUMNS.map(({ key }) => (
                  <td key={key} className="py-2 px-3">
                    <div className="h-4 rounded bg-hs-grid animate-pulse w-3/4" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
            {COLUMNS.map(({ key, label }) => (
              <th
                key={key}
                className="py-2 px-3 text-left font-medium cursor-pointer
                  select-none hover:text-hs-text transition-colors"
                onClick={() => handleSort(key)}
              >
                {label}
                {sortKey === key && (
                  <span className="ml-1">
                    {sortDir === "asc" ? "\u2191" : "\u2193"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {coins.map((snap: LiveSnapshot) => (
            <tr
              key={snap.coin}
              onClick={() => onSelectCoin(snap.coin)}
              className="border-b border-hs-grid hover:bg-hs-mint/50
                cursor-pointer"
            >
              <td className="py-2 px-3 text-hs-green-dark font-medium">
                {snap.coin}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatPrice(snap.mark_price)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatUSD(snap.open_interest_usd)}
              </td>
              <td
                className={`py-2 px-3 tabular-nums ${
                  snap.funding_rate >= 0 ? "text-hs-teal" : "text-hs-red"
                }`}
              >
                {formatFundingRate(snap.funding_rate)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatUSD(snap.day_volume_usd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
