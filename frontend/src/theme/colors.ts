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
