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
  toggle: (key: string) => void;
  isVisible: (key: string, defaultVisible?: boolean) => boolean;
}

export const usePanelStore = create<PanelStore>()(
  persist(
    (set, get) => ({
      panels: {},
      toggle: (key) =>
        set((s) => ({
          panels: { ...s.panels, [key]: !s.panels[key] },
        })),
      isVisible: (key, defaultVisible = true) => {
        const val = get().panels[key];
        return val === undefined ? defaultVisible : val;
      },
    }),
    { name: "hs-panels" }
  )
);
