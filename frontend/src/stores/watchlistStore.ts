/**
 * Persisted watchlist store — pin coins and wallets for quick access
 * from the sidebar regardless of which page you're on.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type WatchlistKind = "coin" | "wallet";

export interface WatchlistItem {
  kind: WatchlistKind;
  id: string;
  /** Optional display label (currently used for wallets only). */
  label?: string;
  addedAt: number;
}

interface WatchlistStore {
  items: WatchlistItem[];
  add: (kind: WatchlistKind, id: string, label?: string) => void;
  remove: (kind: WatchlistKind, id: string) => void;
  toggle: (kind: WatchlistKind, id: string, label?: string) => void;
}

const watchKey = (kind: WatchlistKind, id: string) => `${kind}:${id}`;

export const useWatchlistStore = create<WatchlistStore>()(
  persist(
    (set, get) => ({
      items: [],
      add: (kind, id, label) => {
        const key = watchKey(kind, id);
        if (get().items.some((it) => watchKey(it.kind, it.id) === key)) return;
        set((s) => ({
          items: [...s.items, { kind, id, label, addedAt: Date.now() }],
        }));
      },
      remove: (kind, id) => {
        const key = watchKey(kind, id);
        set((s) => ({
          items: s.items.filter((it) => watchKey(it.kind, it.id) !== key),
        }));
      },
      toggle: (kind, id, label) => {
        const key = watchKey(kind, id);
        const exists = get().items.some(
          (it) => watchKey(it.kind, it.id) === key,
        );
        if (exists) {
          get().remove(kind, id);
        } else {
          get().add(kind, id, label);
        }
      },
    }),
    { name: "hs-watchlist" },
  ),
);

/** Subscribe to whether a single (kind, id) is currently watched. */
export function useIsWatched(kind: WatchlistKind, id: string): boolean {
  return useWatchlistStore((s) =>
    s.items.some((it) => it.kind === kind && it.id === id),
  );
}
