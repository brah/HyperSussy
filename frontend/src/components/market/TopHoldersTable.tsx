import { AddressLink } from "../common/AddressLink";
import { formatUSD } from "../../utils/format";
import type { TopHolderItem } from "../../api/types";

interface TopHoldersTableProps {
  coin: string;
  hours: number;
  holders: TopHolderItem[];
}

/** Top holders ranked by position size for a given coin. */
export function TopHoldersTable({
  coin,
  hours,
  holders,
}: Readonly<TopHoldersTableProps>) {
  if (holders.length === 0) return null;

  return (
    <div className="bg-hs-surface border border-hs-grid rounded-lg p-4">
      <h2 className="text-hs-text font-medium mb-3">
        Top Holders — {coin} ({hours}h)
      </h2>
      <div className="divide-y divide-hs-grid">
        {holders
          .slice()
          .sort((a, b) => b.volume_usd - a.volume_usd)
          .slice(0, 10)
          .map((h, idx) => {
            const sharePct =
              h.total_volume > 0
                ? (h.volume_usd / h.total_volume) * 100
                : null;
            return (
              <div
                key={h.address}
                className="flex items-center justify-between py-2"
              >
                <div className="flex items-center gap-3">
                  <span className="text-hs-grey text-sm w-5">{idx + 1}</span>
                  <AddressLink address={h.address} />
                </div>
                <div className="text-right">
                  <span className="text-hs-text tabular-nums text-sm">
                    {formatUSD(h.volume_usd)}
                  </span>
                  {sharePct != null && (
                    <span className="ml-2 text-xs text-hs-grey tabular-nums">
                      {sharePct.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
