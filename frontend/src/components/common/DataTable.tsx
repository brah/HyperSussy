import { useMemo, useState, type ReactNode } from "react";

type SortDir = "asc" | "desc";
type SortValue = string | number | null;

export interface Column<T> {
  /** Stable column id (used for sort state, header keys). */
  id: string;
  /** Header label. */
  header: string;
  /** Pull a sortable scalar from a row. Sort disabled when omitted. */
  accessor?: (row: T) => SortValue;
  /** Render the cell. Defaults to `String(accessor(row) ?? "")`. */
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  /** Extra classes on the `<th>`. */
  headerClassName?: string;
  /** Static or per-row classes on the `<td>`. */
  cellClassName?: string | ((row: T) => string);
  /** Force-disable sorting on a column even if accessor is provided. */
  sortable?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  defaultSortId?: string;
  defaultSortDir?: SortDir;
  /** Optional row selection highlight (mint background). */
  isSelected?: (row: T) => boolean;
  /** Renderable footer (e.g. "Load more" button). */
  footer?: ReactNode;
  /** Empty placeholder content (defaults to a generic message). */
  emptyMessage?: string;
}

const NULL_AS_NEG_INF = -Infinity;

function compareSortValues(a: SortValue, b: SortValue): number {
  // Push null/undefined to the bottom regardless of direction sign-flip
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") {
    // Treat -Infinity guard so callers can return -Infinity to sink rows
    if (a === NULL_AS_NEG_INF && b !== NULL_AS_NEG_INF) return 1;
    if (b === NULL_AS_NEG_INF && a !== NULL_AS_NEG_INF) return -1;
    return a - b;
  }
  return String(a).localeCompare(String(b));
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  defaultSortId,
  defaultSortDir = "desc",
  isSelected,
  footer,
  emptyMessage = "No data",
}: Readonly<DataTableProps<T>>) {
  const [sortId, setSortId] = useState<string | null>(defaultSortId ?? null);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);

  const sortedRows = useMemo(() => {
    if (sortId == null) return rows;
    const col = columns.find((c) => c.id === sortId);
    if (!col?.accessor) return rows;
    const accessor = col.accessor;
    return [...rows].sort((a, b) => {
      const cmp = compareSortValues(accessor(a), accessor(b));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, columns, sortId, sortDir]);

  const toggleSort = (col: Column<T>) => {
    if (col.sortable === false || !col.accessor) return;
    if (sortId === col.id) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortId(col.id);
      setSortDir("desc");
    }
  };

  const alignClass = (a?: Column<T>["align"]) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hs-grid text-hs-grey">
              {columns.map((col) => {
                const sortable = col.sortable !== false && col.accessor != null;
                return (
                  <th
                    key={col.id}
                    className={`py-2 px-3 font-medium select-none whitespace-nowrap ${alignClass(col.align)} ${
                      sortable ? "cursor-pointer hover:text-hs-text" : ""
                    } ${col.headerClassName ?? ""}`}
                    onClick={() => toggleSort(col)}
                  >
                    {col.header}
                    {sortable && sortId === col.id && (
                      <span className="ml-1 text-xs">
                        {sortDir === "asc" ? "↑" : "↓"}
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => {
              const selected = isSelected?.(row) ?? false;
              return (
                <tr
                  key={rowKey(row)}
                  className={`border-b border-hs-grid transition-colors ${
                    selected ? "bg-hs-mint" : "hover:bg-hs-mint/50"
                  }`}
                >
                  {columns.map((col) => {
                    const cellExtra =
                      typeof col.cellClassName === "function"
                        ? col.cellClassName(row)
                        : (col.cellClassName ?? "");
                    return (
                      <td
                        key={col.id}
                        className={`py-2 px-3 ${alignClass(col.align)} ${cellExtra}`}
                      >
                        {col.render
                          ? col.render(row)
                          : String(col.accessor?.(row) ?? "")}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {sortedRows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-8 text-center text-hs-grey"
                >
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {footer}
    </div>
  );
}
