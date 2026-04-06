import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invalidateWhalesQueries } from "../../api/cache";
import { removeWhale } from "../../api/client";
import { whalesQuery } from "../../api/queries";
import { AddressLink } from "../common/AddressLink";
import { EmptyState } from "../common/EmptyState";
import { formatUSD } from "../../utils/format";
import { timeAgo } from "../../utils/time";

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
      <div className="divide-y divide-hs-grid">
        {whales.map((w) => {
          const isSelected = selectedAddress === w.address;
          return (
            <div
              key={w.address}
              onClick={() => onSelect(w.address)}
              className={`px-4 py-2.5 cursor-pointer transition-colors ${
                isSelected
                  ? "bg-hs-mint"
                  : "hover:bg-hs-mint/50"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <AddressLink address={w.address} label={w.label} />
                {w.source === "manual" && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeMutation.mutate(w.address);
                    }}
                    disabled={removingAddress === w.address}
                    className="text-xs text-hs-red transition-colors
                               hover:text-hs-red/70 disabled:opacity-50
                               shrink-0"
                  >
                    {removingAddress === w.address ? "..." : "x"}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-hs-grey">
                <span className="tabular-nums">
                  {formatUSD(w.total_volume_usd)}
                </span>
                {w.last_active_ms && (
                  <span>{timeAgo(w.last_active_ms)}</span>
                )}
                <span className="text-hs-grey/60">{w.source}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
