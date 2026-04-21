/** Design token palette — dark theme matching the candlestick chart aesthetic. */

export const colors = {
  bg: "#0a0a0a",
  surface: "#141414",
  green: "#9fe870",
  greenDark: "#163300",
  teal: "#26a69a",
  red: "#ef5350",
  orange: "#f97316",
  grid: "#262626",
  grey: "#6b7280",
  text: "#e5e7eb",
  mint: "#1e3a1e",
  secondary: "#9ca3af",
} as const;

export type ColorKey = keyof typeof colors;

/**
 * Dark-theme palette for the candlestick chart family.
 *
 * DESIGN.md documents the main UI as Wise-inspired light theme with
 * ``LogModal`` as the sole dark-themed carve-out. The candlestick
 * chart (and its header + pane controls) is the second carve-out:
 * lightweight-charts renders best with a dark canvas and this palette
 * pins the values so future charts don't accrete new hex literals.
 *
 * Anything outside the chart file family should still use the light
 * ``colors`` tokens above.
 */
export const chartDarkColors = {
  bg: "#000000",
  panelBorder: "#1a1a1a",
  paneSeparator: "#1a1a1a",
  paneSeparatorHover: "#2a2a2a",
  text: "#9ca3af",
  legend: "#9ca3af",
  crosshairLine: "#374151",
  crosshairLabelBg: "#1f2937",
  btnHoverBg: "rgba(31,41,55,0.8)",
  btnHoverText: "#e5e7eb",
  btnIdleText: "#6b7280",
  up: "#26a69a",
  down: "#ef5350",
  // Semi-transparent histogram fills that tint the volume bar by
  // whether the candle closed green/red. Baked as ``hex + alpha``
  // (``60`` ≈ 37 %) so callers can pass them directly to LWC.
  volumeUp: "#26a69a60",
  volumeDown: "#ef535060",
  // Area fill for sub-panes that need a subtle tint above the
  // x-axis (e.g. OI pane).
  areaTintTeal: "#26a69a30",
} as const;

/** Ordered palette for multi-coin comparison series (primary first). */
export const compareColors = [
  "#26a69a", // teal   — primary
  "#f97316", // orange — compare 1
  "#ef5350", // red    — compare 2
  "#3b82f6", // blue   — compare 3
  "#a78bfa", // violet — compare 4
] as const;

/** Map alert severity to a CSS color value. */
export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return colors.red;
    case "high":
      return colors.orange;
    case "medium":
      return "#eab308";
    default:
      return colors.grey;
  }
}
