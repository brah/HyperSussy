/**
 * Zustand store for panel visibility, persisted to localStorage.
 *
 * Each panel has a string key and a boolean visible flag. Defaults are
 * defined per-page and applied only when the key has never been stored.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface PanelStore {
  panels: Record<string, boolean>;
  toggle: (key: string, defaultVisible?: boolean) => void;
}

export const usePanelStore = create<PanelStore>()(
  persist(
    (set) => ({
      panels: {},
      toggle: (key, defaultVisible = true) =>
        set((s) => ({
          panels: {
            ...s.panels,
            [key]: !(s.panels[key] ?? defaultVisible),
          },
        })),
    }),
    { name: "hs-panels" }
  )
);

/** Subscribe to a single panel key. Only re-renders when that key changes. */
export function usePanelVisible(
  key: string,
  defaultVisible = true
): boolean {
  return usePanelStore((s) => s.panels[key] ?? defaultVisible);
}
