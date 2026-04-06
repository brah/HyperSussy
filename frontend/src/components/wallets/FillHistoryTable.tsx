import { useInfiniteQuery } from "@tanstack/react-query";
import { fillsInfiniteQuery } from "../../api/queries";
import { EmptyState } from "../common/EmptyState";
import { formatPrice, formatUSD } from "../../utils/format";
import { fmtDatetime } from "../../utils/time";

interface FillHistoryTableProps {
  address: string;
}

const COLUMNS = [
  "Time",
  "Coin",
  "Side",
  "Direction",
  "Price",
  "Size",
  "Closed PnL",
];

/** Paginated fill history from the Hyperliquid API. */
export function FillHistoryTable({
  address,
}: Readonly<FillHistoryTableProps>) {
  const {
    data,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useInfiniteQuery(fillsInfiniteQuery(address));

  const fills = data?.pages.flatMap((p) => p.fills) ?? [];

  if (isLoading) {
    return (
      <p className="py-6 text-center text-sm text-hs-grey animate-pulse">
        Loading fills...
      </p>
    );
  }

  if (isError) {
    return (
      <div className="py-6 text-center text-sm text-hs-red">
        Failed to load fill history
        {error instanceof Error ? `: ${error.message}` : ""}
      </div>
    );
  }

  if (fills.length === 0) {
    return <EmptyState message="No fill history found for this address." />;
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hs-grid text-hs-grey">
              {COLUMNS.map((h) => (
                <th key={h} className="py-2 px-3 text-left font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fills.map((f, idx) => {
              const isBuy = f.side === "B";
              const pnlNonZero = Math.abs(f.closed_pnl) > 0.001;
              return (
                <tr
                  key={`${f.oid}-${f.time}-${idx}`}
                  className="border-b border-hs-grid hover:bg-hs-mint/50"
                >
                  <td className="py-2 px-3 text-hs-grey text-xs whitespace-nowrap">
                    {fmtDatetime(f.time)}
                  </td>
                  <td className="py-2 px-3 text-hs-text">{f.coin}</td>
                  <td
                    className={`py-2 px-3 font-medium ${
                      isBuy ? "text-hs-teal" : "text-hs-red"
                    }`}
                  >
                    {isBuy ? "Buy" : "Sell"}
                  </td>
                  <td className="py-2 px-3 text-hs-secondary text-xs">
                    {f.dir}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {formatPrice(f.px)}
                  </td>
                  <td className="py-2 px-3 text-hs-text tabular-nums">
                    {f.sz.toFixed(4)}
                  </td>
                  <td
                    className={`py-2 px-3 tabular-nums ${
                      !pnlNonZero
                        ? "text-hs-grey"
                        : f.closed_pnl >= 0
                        ? "text-hs-teal"
                        : "text-hs-red"
                    }`}
                  >
                    {pnlNonZero
                      ? `${f.closed_pnl >= 0 ? "+" : ""}${formatUSD(f.closed_pnl)}`
                      : "-"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {hasNextPage && (
        <div className="flex justify-center py-3 border-t border-hs-grid">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="rounded-full bg-hs-green px-4 py-1.5 text-sm
                       font-semibold text-hs-green-dark transition-all
                       wise-interactive disabled:opacity-50"
          >
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
