import { AddressLink } from "../common/AddressLink";
import { formatUSD } from "../../utils/format";
import type { TopWhaleItem } from "../../api/types";

interface TopTradersTableProps {
  coin: string;
  hours: number;
  traders: TopWhaleItem[];
}

/** Top traders ranked by volume for a given coin. */
export function TopTradersTable({
  coin,
  hours,
  traders,
}: Readonly<TopTradersTableProps>) {
  if (traders.length === 0) return null;

  return (
    <div className="bg-hs-surface border border-hs-grid rounded-lg p-4">
      <h2 className="text-hs-text font-medium mb-3">
        Top Volume — {coin} ({hours}h)
      </h2>
      <div className="divide-y divide-hs-grid">
        {traders.slice(0, 10).map((w, idx) => (
          <div
            key={w.address}
            className="flex items-center justify-between py-2"
          >
            <div className="flex items-center gap-3">
              <span className="text-hs-grey text-sm w-5">{idx + 1}</span>
              <AddressLink address={w.address} />
            </div>
            <span className="text-hs-text tabular-nums text-sm">
              {formatUSD(w.volume_usd)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
