import { useMemo } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { fillsInfiniteQuery } from "../../api/queries";
import type { FillItem } from "../../api/types";
import { CoinLink } from "../common/CoinLink";
import { DataTable, type Column } from "../common/DataTable";
import { EmptyState } from "../common/EmptyState";
import { formatPrice, formatSize, formatUSD } from "../../utils/format";
import { fmtDatetime } from "../../utils/time";

interface FillHistoryTableProps {
  address: string;
}

const PNL_EPS = 0.001;

const COLUMNS: Column<FillItem>[] = [
  {
    id: "time",
    header: "Time",
    accessor: (f) => f.time,
    render: (f) => (
      <span className="text-hs-grey text-xs whitespace-nowrap">
        {fmtDatetime(f.time)}
      </span>
    ),
  },
  {
    id: "coin",
    header: "Coin",
    accessor: (f) => f.coin,
    render: (f) => <CoinLink coin={f.coin} />,
  },
  {
    id: "side",
    header: "Side",
    accessor: (f) => f.side,
    render: (f) => {
      const isBuy = f.side === "B";
      return (
        <span
          className={`font-medium ${isBuy ? "text-hs-teal" : "text-hs-red"}`}
        >
          {isBuy ? "Buy" : "Sell"}
        </span>
      );
    },
  },
  {
    id: "dir",
    header: "Direction",
    accessor: (f) => f.dir,
    render: (f) => <span className="text-hs-secondary text-xs">{f.dir}</span>,
  },
  {
    id: "px",
    header: "Price",
    accessor: (f) => f.px,
    render: (f) => formatPrice(f.px),
    cellClassName: "text-hs-text tabular-nums",
  },
  {
    id: "sz",
    header: "Size",
    accessor: (f) => f.sz,
    render: (f) => formatSize(f.sz),
    cellClassName: "text-hs-text tabular-nums",
  },
  {
    id: "closed_pnl",
    header: "Closed PnL",
    accessor: (f) => f.closed_pnl,
    render: (f) => {
      const pnlNonZero = Math.abs(f.closed_pnl) > PNL_EPS;
      if (!pnlNonZero) return "-";
      const sign = f.closed_pnl >= 0 ? "+" : "";
      return `${sign}${formatUSD(f.closed_pnl)}`;
    },
    cellClassName: (f) => {
      const pnlNonZero = Math.abs(f.closed_pnl) > PNL_EPS;
      if (!pnlNonZero) return "text-hs-grey tabular-nums";
      return f.closed_pnl >= 0
        ? "text-hs-teal tabular-nums"
        : "text-hs-red tabular-nums";
    },
  },
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

  // flatMap allocates a new array on every call; memoise so unrelated
  // parent re-renders don't reshape the table rows.
  const fills = useMemo(
    () => data?.pages.flatMap((p) => p.fills) ?? [],
    [data?.pages],
  );

  if (isLoading) {
    return <EmptyState message="Loading fills..." state="loading" compact />;
  }

  if (isError) {
    return (
      <EmptyState
        message="Failed to load fill history"
        state="error"
        error={error}
        compact
      />
    );
  }

  if (fills.length === 0) {
    return <EmptyState message="No fill history found for this address." />;
  }

  return (
    <DataTable
      columns={COLUMNS}
      rows={fills}
      rowKey={(f) => `${f.oid}-${f.time}-${f.hash}`}
      footer={
        hasNextPage && (
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
        )
      }
    />
  );
}
