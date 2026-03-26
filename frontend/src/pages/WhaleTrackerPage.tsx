import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { whalesQuery } from "../api/queries";
import { addWhale, removeWhale } from "../api/client";
import { AddressLink } from "../components/common/AddressLink";
import { PageHeader } from "../components/layout/PageHeader";
import { EmptyState } from "../components/common/EmptyState";
import { normalizeAddress, formatUSD } from "../utils/format";
import { fmtDatetime } from "../utils/time";

export function WhaleTrackerPage() {
  const [newAddress, setNewAddress] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [formError, setFormError] = useState("");

  const queryClient = useQueryClient();
  const { data: whales = [] } = useQuery(whalesQuery(200));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["whales"] });
  };

  const addMutation = useMutation({
    mutationFn: ({ address, label }: { address: string; label: string }) =>
      addWhale(address, label),
    onSuccess: () => {
      setNewAddress("");
      setNewLabel("");
      setFormError("");
      invalidate();
    },
    onError: (err: Error) => {
      setFormError(err.message);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (address: string) => removeWhale(address),
    onSuccess: invalidate,
  });

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const addr = normalizeAddress(newAddress);
    if (!addr) {
      setFormError("Invalid 0x address (must be 42 characters).");
      return;
    }
    setFormError("");
    addMutation.mutate({ address: addr, label: newLabel });
  }

  return (
    <div>
      <PageHeader title="Whale Tracker" />

      {/* Add address form */}
      <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg p-4 mb-6">
        <h2 className="text-[#fafafa] font-medium mb-3">Add Address</h2>
        <form onSubmit={handleAdd} className="flex gap-3 flex-wrap">
          <input
            type="text"
            value={newAddress}
            onChange={(e) => setNewAddress(e.target.value)}
            placeholder="0x address (42 chars)"
            className="flex-1 min-w-48 bg-[#0e1117] border border-[#2a2d35] text-[#fafafa]
                       text-sm rounded px-3 py-1.5 placeholder-[#4a4e69]
                       focus:outline-none focus:border-[#00d4aa]"
          />
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label (optional)"
            className="w-40 bg-[#0e1117] border border-[#2a2d35] text-[#fafafa]
                       text-sm rounded px-3 py-1.5 placeholder-[#4a4e69]
                       focus:outline-none focus:border-[#00d4aa]"
          />
          <button
            type="submit"
            disabled={addMutation.isPending}
            className="px-4 py-1.5 bg-[#00d4aa] text-[#0e1117] text-sm font-semibold
                       rounded hover:bg-[#00d4aa]/80 transition-colors disabled:opacity-50"
          >
            {addMutation.isPending ? "Adding…" : "Add"}
          </button>
        </form>
        {formError && (
          <p className="text-[#ff4b4b] text-xs mt-2">{formError}</p>
        )}
      </div>

      {/* Whale list */}
      <div className="bg-[#141a22] border border-[#2a2d35] rounded-lg">
        <div className="p-4 border-b border-[#2a2d35]">
          <h2 className="text-[#fafafa] font-medium">
            Tracked Addresses ({whales.length})
          </h2>
        </div>
        {whales.length === 0 ? (
          <EmptyState message="No tracked addresses yet. Add one above." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2a2d35] text-[#4a4e69]">
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
                    className="border-b border-[#2a2d35] hover:bg-[#0e1117]"
                  >
                    <td className="py-2 px-3">
                      <AddressLink address={w.address} label={null} />
                    </td>
                    <td className="py-2 px-3 text-[#4a4e69]">
                      {w.label ?? "—"}
                    </td>
                    <td className="py-2 px-3 text-[#fafafa] tabular-nums">
                      {formatUSD(w.total_volume_usd)}
                    </td>
                    <td className="py-2 px-3 text-[#4a4e69] text-xs">
                      {w.last_active_ms ? fmtDatetime(w.last_active_ms) : "—"}
                    </td>
                    <td className="py-2 px-3 text-[#4a4e69]">{w.source}</td>
                    <td className="py-2 px-3">
                      {w.source === "manual" && (
                        <button
                          onClick={() =>
                            removeMutation.mutate(w.address)
                          }
                          disabled={removeMutation.isPending}
                          className="text-[#ff4b4b] hover:text-[#ff4b4b]/70 text-xs
                                     transition-colors disabled:opacity-50"
                        >
                          Remove
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
