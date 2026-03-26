import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { invalidateWhalesQueries } from "../api/cache";
import { whalesQuery } from "../api/queries";
import { removeWhale } from "../api/client";
import { AddressLink } from "../components/common/AddressLink";
import { PageHeader } from "../components/layout/PageHeader";
import { EmptyState } from "../components/common/EmptyState";
import { formatUSD } from "../utils/format";
import { fmtDatetime } from "../utils/time";
import { AddWhaleForm } from "../components/whales/AddWhaleForm";

export function WhaleTrackerPage() {
  const [removeError, setRemoveError] = useState("");
  const queryClient = useQueryClient();
  const { data: whales = [] } = useQuery(whalesQuery(200));

  const removeMutation = useMutation({
    mutationFn: (address: string) => removeWhale(address),
    onMutate: () => {
      setRemoveError("");
    },
    onSuccess: () => {
      void invalidateWhalesQueries(queryClient);
    },
    onError: (err: Error) => {
      setRemoveError(err.message);
    },
  });
  const removingAddress = removeMutation.isPending ? removeMutation.variables : null;

  return (
    <div>
      <PageHeader title="Whale Tracker" />

      <AddWhaleForm />

      <div className="rounded-lg border border-hs-grid bg-hs-surface">
        <div className="border-b border-hs-grid p-4">
          <h2 className="font-medium text-hs-text">
            Tracked Addresses ({whales.length})
          </h2>
        </div>

        {removeError && (
          <p className="border-b border-hs-grid bg-hs-bg px-4 py-2 text-sm text-hs-red">
            Failed to remove address: {removeError}
          </p>
        )}

        {whales.length === 0 ? (
          <EmptyState message="No tracked addresses yet. Add one above." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hs-grid text-hs-grey">
                  {["Address", "Label", "Total Volume", "Last Active", "Source", ""].map(
                    (h) => (
                      <th key={h} className="py-2 px-3 text-left font-medium">
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {whales.map((w) => (
                  <tr
                    key={w.address}
                    className="border-b border-hs-grid hover:bg-hs-bg"
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
                    <td className="py-2 px-3">
                      {w.source === "manual" && (
                        <button
                          onClick={() => removeMutation.mutate(w.address)}
                          disabled={removingAddress === w.address}
                          className="text-xs text-hs-red transition-colors hover:text-hs-red/70
                                     disabled:opacity-50"
                        >
                          {removingAddress === w.address ? "Removing..." : "Remove"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
