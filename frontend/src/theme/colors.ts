/** Design token palette — Wise design system. */

export const colors = {
  bg: "#ffffff",
  surface: "#f8faf6",
  green: "#9fe870",
  greenDark: "#163300",
  teal: "#054d28",
  red: "#d03238",
  orange: "#c65102",
  grid: "#e0e2dc",
  grey: "#868685",
  text: "#0e0f0c",
  mint: "#e2f6d5",
  secondary: "#454745",
} as const;

export type ColorKey = keyof typeof colors;

/** Map alert severity to a CSS color value (WCAG-safe on white). */
export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return colors.red;
    case "high":
      return colors.orange;
    case "medium":
      return "#946800";
    default:
      return colors.grey;
  }
}
