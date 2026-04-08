import { DataTable, type Column } from "../common/DataTable";
import { EmptyState } from "../common/EmptyState";
import { formatUSD } from "../../utils/format";
import type { SpotAssetItem } from "../../api/types";

interface SpotAssetsTableProps {
  assets: SpotAssetItem[];
}

const columns: Column<SpotAssetItem>[] = [
  {
    id: "coin",
    header: "Token",
    accessor: (a) => a.coin,
    render: (a) => (
      <span className="font-mono font-semibold text-hs-green">{a.coin}</span>
    ),
  },
  {
    id: "total",
    header: "Balance",
    accessor: (a) => a.total,
    render: (a) => (
      <span className="tabular-nums">
        {a.total.toLocaleString(undefined, { maximumFractionDigits: 6 })}
      </span>
    ),
    cellClassName: "text-hs-text tabular-nums",
  },
  {
    id: "hold",
    header: "In Orders",
    accessor: (a) => a.hold,
    render: (a) =>
      a.hold > 0
        ? a.hold.toLocaleString(undefined, { maximumFractionDigits: 6 })
        : "—",
    cellClassName: "text-hs-grey tabular-nums",
  },
  {
    id: "entry_ntl",
    header: "Notional (USD)",
    accessor: (a) => a.entry_ntl,
    render: (a) => (a.entry_ntl > 0 ? formatUSD(a.entry_ntl) : "—"),
    cellClassName: "text-hs-text tabular-nums",
  },
];

/** Spot token holdings for a wallet address. */
export function SpotAssetsTable({ assets }: Readonly<SpotAssetsTableProps>) {
  if (assets.length === 0) {
    return <EmptyState message="No spot token balances." />;
  }

  return (
    <DataTable
      columns={columns}
      rows={assets}
      rowKey={(a) => a.coin}
      defaultSortId="entry_ntl"
    />
  );
}
