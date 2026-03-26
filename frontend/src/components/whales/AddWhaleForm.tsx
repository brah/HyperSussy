import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addWhale } from "../../api/client";
import { invalidateWhalesQueries } from "../../api/cache";
import { normalizeAddress } from "../../utils/format";

export function AddWhaleForm() {
  const [newAddress, setNewAddress] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [formError, setFormError] = useState("");

  const queryClient = useQueryClient();

  const addMutation = useMutation({
    mutationFn: ({ address, label }: { address: string; label: string }) =>
      addWhale(address, label),
    onSuccess: () => {
      setNewAddress("");
      setNewLabel("");
      setFormError("");
      void invalidateWhalesQueries(queryClient);
    },
    onError: (err: Error) => {
      setFormError(err.message);
    },
  });

  function handleAdd(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const address = normalizeAddress(newAddress);
    if (!address) {
      setFormError("Invalid 0x address (must be 42 characters).");
      return;
    }

    setFormError("");
    addMutation.mutate({ address, label: newLabel.trim() });
  }

  return (
    <div className="mb-6 rounded-lg border border-hs-grid bg-hs-surface p-4">
      <div className="mb-3">
        <h2 className="font-medium text-hs-text">Add Address</h2>
        <p className="mt-1 text-sm text-hs-grey">
          Track a manual whale wallet by entering its full wallet address.
        </p>
      </div>

      <form
        onSubmit={handleAdd}
        className="flex flex-col gap-4 lg:flex-row lg:items-end"
      >
        <div className="min-w-64 flex-1">
          <label
            htmlFor="whale-address"
            className="mb-1 block text-xs font-medium uppercase tracking-wider text-hs-grey"
          >
            Address
          </label>
          <input
            id="whale-address"
            type="text"
            value={newAddress}
            onChange={(e) => setNewAddress(e.target.value)}
            placeholder="0x address (42 chars)"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={formError.length > 0}
            className="w-full rounded border border-hs-grid bg-hs-bg px-3 py-1.5 text-sm text-hs-text
                       placeholder-hs-grey focus:border-hs-green focus:outline-none"
          />
          <p className="mt-1 text-xs text-hs-grey">
            Use the canonical 42-character 0x wallet address.
          </p>
        </div>

        <div className="w-full lg:w-52">
          <label
            htmlFor="whale-label"
            className="mb-1 block text-xs font-medium uppercase tracking-wider text-hs-grey"
          >
            Label
          </label>
          <input
            id="whale-label"
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Optional label"
            autoComplete="off"
            className="w-full rounded border border-hs-grid bg-hs-bg px-3 py-1.5 text-sm text-hs-text
                       placeholder-hs-grey focus:border-hs-green focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={addMutation.isPending}
          className="rounded bg-hs-green px-4 py-1.5 text-sm font-semibold text-hs-bg
                     transition-colors hover:bg-hs-green/80 disabled:opacity-50"
        >
          {addMutation.isPending ? "Adding..." : "Add"}
        </button>
      </form>

      {formError && <p className="mt-2 text-xs text-hs-red">{formError}</p>}
    </div>
  );
}
