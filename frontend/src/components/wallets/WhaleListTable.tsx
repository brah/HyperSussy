import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invalidateWhalesQueries } from "../../api/cache";
import { removeWhale } from "../../api/client";
import { whalesQuery } from "../../api/queries";
import { AddressLink } from "../common/AddressLink";
import { EmptyState } from "../common/EmptyState";
import { formatUSD } from "../../utils/format";
import { fmtDatetime } from "../../utils/time";

interface WhaleListTableProps {
  selectedAddress: string | null;
  onSelect: (address: string) => void;
}

/** Tracked whale addresses table with inline remove and row selection. */
export function WhaleListTable({
  selectedAddress,
  onSelect,
}: Readonly<WhaleListTableProps>) {
  const [removeError, setRemoveError] = useState("");
  const queryClient = useQueryClient();
  const { data: whales = [] } = useQuery(whalesQuery(200));

  const removeMutation = useMutation({
    mutationFn: (address: string) => removeWhale(address),
    onMutate: () => {
      setRemoveError("");
    },
    onSuccess: () => void invalidateWhalesQueries(queryClient),
    onError: (err: Error) => {
      setRemoveError(err.message);
    },
  });
  const removingAddress = removeMutation.isPending
    ? removeMutation.variables
    : null;

  if (whales.length === 0) {
    return <EmptyState message="No tracked addresses yet. Add one above." />;
  }

  return (
    <div>
      {removeError && (
        <p className="border-b border-hs-grid bg-hs-bg px-4 py-2 text-sm text-hs-red">
          Failed to remove address: {removeError}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hs-grid text-hs-grey">
              {["Address", "Label", "Volume", "Last Active", "Source", ""].map(
                (h) => (
                  <th key={h} className="py-2 px-3 text-left font-medium">
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {whales.map((w) => {
              const isSelected = selectedAddress === w.address;
              return (
                <tr
                  key={w.address}
                  onClick={() => onSelect(w.address)}
                  className={`border-b border-hs-grid cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-hs-mint"
                      : "hover:bg-hs-mint/50"
                  }`}
                >
                  <td className="py-2 px-3">
                    <AddressLink address={w.address} label={null} />
                  </td>
                  <td className="py-2 px-3 text-hs-grey">{w.label ?? "-"}</td>
                  <td className="py-2 px-3 tabular-nums text-hs-text">
                    {formatUSD(w.total_volume_usd)}
                  </td>
                  <td className="py-2 px-3 text-xs text-hs-grey">
                    {w.last_active_ms ? fmtDatetime(w.last_active_ms) : "-"}
                  </td>
                  <td className="py-2 px-3 text-hs-grey">{w.source}</td>
                  <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
                    {w.source === "manual" && (
                      <button
                        onClick={() => removeMutation.mutate(w.address)}
                        disabled={removingAddress === w.address}
                        className="text-xs text-hs-red transition-colors
                                   hover:text-hs-red/70 disabled:opacity-50"
                      >
                        {removingAddress === w.address ? "Removing..." : "Remove"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
