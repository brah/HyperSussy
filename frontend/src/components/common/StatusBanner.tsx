import type { HealthResponse } from "../../api/types";
import { timeAgo } from "../../utils/time";

interface StatusBannerProps {
  health: HealthResponse | null;
  connected: boolean;
}

export function StatusBanner({ health, connected }: StatusBannerProps) {
  const hasErrors =
    (health?.engine_errors.length ?? 0) > 0 ||
    (health?.runtime_errors.length ?? 0) > 0;

  const dotColor = connected && health?.is_running
    ? "bg-[#00d4aa]"
    : hasErrors
    ? "bg-[#ff4b4b]"
    : "bg-[#ffa500]";

  const label = !connected
    ? "Disconnected"
    : health?.is_running
    ? "Live"
    : "Stopped";

  return (
    <div className="flex items-center gap-3 text-sm text-[#4a4e69]">
      <span className={`inline-block w-2 h-2 rounded-full ${dotColor}`} />
      <span className="text-[#fafafa] font-medium">{label}</span>
      {health?.last_snapshot_ms && (
        <span>Last snapshot {timeAgo(health.last_snapshot_ms)}</span>
      )}
      {hasErrors && (
        <span className="text-[#ff4b4b]">
          {health!.engine_errors.length + health!.runtime_errors.length} error(s)
        </span>
      )}
    </div>
  );
}
