import { useState } from "react";

type SortDir = "asc" | "desc";

interface Column<T> {
  key: keyof T;
  header: string;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
  align?: "left" | "right";
}

interface DataTableProps<T extends Record<string, unknown>> {
  columns: Column<T>[];
  rows: T[];
  rowKey: keyof T;
  defaultSortKey?: keyof T;
  defaultSortDir?: SortDir;
  maxRows?: number;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  rowKey,
  defaultSortKey,
  defaultSortDir = "desc",
  maxRows,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<keyof T | null>(defaultSortKey ?? null);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);

  const sorted = sortKey
    ? [...rows].sort((a, b) => {
        const av = a[sortKey];
        const bv = b[sortKey];
        const cmp =
          typeof av === "number" && typeof bv === "number"
            ? av - bv
            : String(av).localeCompare(String(bv));
        return sortDir === "asc" ? cmp : -cmp;
      })
    : rows;

  const displayed = maxRows ? sorted.slice(0, maxRows) : sorted;

  function toggleSort(key: keyof T) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hs-grid text-hs-grey">
            {columns.map((col) => (
              <th
                key={String(col.key)}
                className={`py-2 px-3 font-medium cursor-pointer select-none
                  hover:text-hs-text transition-colors
                  ${col.align === "right" ? "text-right" : "text-left"}`}
                onClick={() => toggleSort(col.key)}
              >
                {col.header}
                {sortKey === col.key && (
                  <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayed.map((row) => (
            <tr
              key={String(row[rowKey])}
              className="border-b border-hs-grid hover:bg-hs-mint/50 transition-colors"
            >
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className={`py-2 px-3 text-hs-text
                    ${col.align === "right" ? "text-right tabular-nums" : ""}`}
                >
                  {col.render
                    ? col.render(row[col.key], row)
                    : String(row[col.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
          {displayed.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="py-8 text-center text-hs-grey"
              >
                No data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
