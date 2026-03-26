import { EmptyState } from "../common/EmptyState";
import { formatPrice, formatUSD } from "../../utils/format";
import type { PositionItem } from "../../api/types";

interface PositionsTableProps {
  positions: PositionItem[];
}

/** Open positions for a single wallet address. */
export function PositionsTable({ positions }: Readonly<PositionsTableProps>) {
  if (positions.length === 0) {
    return <EmptyState message="No open positions." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
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
            <tr key={p.coin} className="border-b border-hs-grid hover:bg-hs-bg">
              <td className="py-2 px-3 text-hs-text font-medium">{p.coin}</td>
              <td
                className={`py-2 px-3 tabular-nums ${
                  p.size >= 0 ? "text-hs-green" : "text-hs-red"
                }`}
              >
                {p.size.toFixed(4)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatUSD(p.notional_usd)}
              </td>
              <td
                className={`py-2 px-3 tabular-nums ${
                  p.unrealized_pnl >= 0 ? "text-hs-green" : "text-hs-red"
                }`}
              >
                {formatUSD(p.unrealized_pnl)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {formatPrice(p.mark_price)}
              </td>
              <td className="py-2 px-3 text-hs-text tabular-nums">
                {p.liquidation_price != null
                  ? formatPrice(p.liquidation_price)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
