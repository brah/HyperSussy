/**
 * Zustand store for chart indicator toggles, persisted to localStorage.
 *
 * Each indicator has a string key and a boolean on/off flag.
 * Follows the same pattern as panelStore.ts.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface IndicatorStore {
  indicators: Record<string, boolean>;
  toggle: (key: string, defaultOn?: boolean) => void;
}

export const useIndicatorStore = create<IndicatorStore>()(
  persist(
    (set) => ({
      indicators: {},
      toggle: (key, defaultOn = false) =>
        set((s) => ({
          indicators: {
            ...s.indicators,
            [key]: !(s.indicators[key] ?? defaultOn),
          },
        })),
    }),
    { name: "hs-indicators" },
  ),
);

/** Subscribe to a single indicator key. Only re-renders when that key changes. */
export function useIndicator(key: string, defaultOn = false): boolean {
  return useIndicatorStore((s) => s.indicators[key] ?? defaultOn);
}
