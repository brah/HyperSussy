import { colors } from "../../theme/colors";

export type Severity = "critical" | "high" | "medium" | "low";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: colors.red,
  high: colors.orange,
  medium: "#946800",
  low: colors.grey,
};

interface SeverityFilterBarProps {
  counts: Record<Severity, number>;
  active: Severity | null;
  onToggle: (sev: Severity | null) => void;
}

/**
 * Row of clickable severity pills that filter an alert feed.
 * Clicking an active filter deactivates it (shows all).
 */
export function SeverityFilterBar({
  counts,
  active,
  onToggle,
}: Readonly<SeverityFilterBarProps>) {
  return (
    <div className="flex flex-wrap gap-2 mb-3">
      {SEVERITY_ORDER.map((sev) => {
        const isActive = active === sev;
        return (
          <button
            key={sev}
            onClick={() => onToggle(isActive ? null : sev)}
            className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs
                        border transition-colors ${
                          isActive
                            ? "border-current bg-current/10"
                            : "border-hs-grid bg-hs-surface hover:border-current/50"
                        }`}
            style={{ color: SEVERITY_COLORS[sev] }}
          >
            <span className="capitalize font-medium">{sev}</span>
            <span
              className="font-semibold"
              style={{ color: isActive ? SEVERITY_COLORS[sev] : colors.text }}
            >
              {counts[sev] ?? 0}
            </span>
          </button>
        );
      })}
    </div>
  );
}
