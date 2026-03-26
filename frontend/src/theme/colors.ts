/** Design token palette — mirrors formatting.py color constants. */

export const colors = {
  bg: "#0e1117",
  surface: "#141a22",
  green: "#00d4aa",
  teal: "#00d4aa",
  red: "#ff4b4b",
  orange: "#ffa500",
  grid: "#2a2d35",
  grey: "#4a4e69",
  text: "#fafafa",
} as const;

export type ColorKey = keyof typeof colors;

/** Map alert severity to a CSS color value. */
export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return colors.red;
    case "high":
      return colors.orange;
    case "medium":
      return "#f59e0b"; // amber
    default:
      return colors.grey;
  }
}
