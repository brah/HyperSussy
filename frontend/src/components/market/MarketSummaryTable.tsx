import { useWsStore } from "../../api/websocket";
import { formatPrice, formatUSD, formatFundingRate } from "../../utils/format";

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
  const coins = Object.values(snapshots).sort(
    (a, b) => b.open_interest_usd - a.open_interest_usd
  );

  if (coins.length === 0) {
    return (
      <p className="text-hs-grey text-sm py-8 text-center">
        Waiting for live data...
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
            {["Coin", "Mark Price", "OI (USD)", "Funding Rate", "24h Volume"].map(
              (h) => (
                <th key={h} className="py-2 px-3 text-left font-medium">
                  {h}
                </th>
              )
            )}
          </tr>
        </thead>
        <tbody>
          {coins.map((snap) => (
            <tr
              key={snap.coin}
              onClick={() => onSelectCoin(snap.coin)}
              className="border-b border-hs-grid hover:bg-hs-surface cursor-pointer"
            >
              <td className="py-2 px-3 text-hs-green font-medium">
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
                  snap.funding_rate >= 0 ? "text-hs-green" : "text-hs-red"
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
