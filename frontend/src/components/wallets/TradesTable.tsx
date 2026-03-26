import { EmptyState } from "../common/EmptyState";
import { formatPrice, formatUSD } from "../../utils/format";
import { fmtDatetime } from "../../utils/time";
import type { TradeItem } from "../../api/types";

interface TradesTableProps {
  trades: TradeItem[];
  hours: number;
}

/** Recent trades for a single wallet address. */
export function TradesTable({ trades, hours }: Readonly<TradesTableProps>) {
  if (trades.length === 0) {
    return <EmptyState message={`No trades in the last ${hours}h.`} />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
            {["Time", "Coin", "Side", "Price", "Size", "Volume"].map((h) => (
              <th key={h} className="py-2 px-3 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr
              key={t.tid}
              className="border-b border-hs-grid hover:bg-hs-bg"
            >
              <td className="py-2 px-3 text-hs-grey text-xs">
                {fmtDatetime(t.timestamp_ms)}
              </td>
              <td className="py-2 px-3 text-hs-text">{t.coin}</td>
              <td
                className={`py-2 px-3 font-medium ${
                  t.side === "B" ? "text-hs-green" : "text-hs-red"
                }`}
              >
                {t.side === "B" ? "Buy" : "Sell"}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatPrice(t.price)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {t.size.toFixed(4)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatUSD(t.price * t.size)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
