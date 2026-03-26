import type { HealthResponse } from "../../api/types";
import { timeAgo } from "../../utils/time";

interface StatusBannerProps {
  health: HealthResponse | null;
  connected: boolean;
}

export function StatusBanner({ health, connected }: StatusBannerProps) {
  const errorCount =
    (health?.engine_errors.length ?? 0) + (health?.runtime_errors.length ?? 0);
  const hasErrors = errorCount > 0;

  const dotColor = connected && health?.is_running
    ? "bg-hs-green"
    : hasErrors
    ? "bg-hs-red"
    : "bg-hs-orange";

  const label = !connected
    ? "Disconnected"
    : health?.is_running
    ? "Live"
    : "Stopped";

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-hs-grey">
      <span className={`inline-block h-2 w-2 rounded-full ${dotColor}`} />
      <span className="font-medium text-hs-text">{label}</span>
      {health?.last_snapshot_ms && (
        <span>Last snapshot {timeAgo(health.last_snapshot_ms)}</span>
      )}
      {hasErrors && (
        <span className="text-hs-red">{errorCount} error(s)</span>
      )}
    </div>
  );
}
