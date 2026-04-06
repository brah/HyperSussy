import { useState } from "react";
import type { HealthResponse } from "../../api/types";
import { timeAgo } from "../../utils/time";
import { LogModal } from "./LogModal";

interface StatusBannerProps {
  health: HealthResponse | null;
  connected: boolean;
}

function dotColor(connected: boolean, isRunning: boolean, hasErrors: boolean): string {
  if (connected && isRunning) return "bg-hs-teal";
  if (hasErrors) return "bg-hs-red";
  return "bg-hs-orange";
}

function statusLabel(connected: boolean, isRunning: boolean): string {
  if (!connected) return "Disconnected";
  return isRunning ? "Live" : "Stopped";
}

export function StatusBanner({ health, connected }: Readonly<StatusBannerProps>) {
  const [showLogs, setShowLogs] = useState(false);

  const errorCount =
    (health?.engine_errors.length ?? 0) + (health?.runtime_errors.length ?? 0);
  const hasErrors = errorCount > 0;
  const isRunning = health?.is_running ?? false;

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-hs-grey">
        <span
          className={`inline-block h-2 w-2 rounded-full ${dotColor(
            connected,
            isRunning,
            hasErrors
          )}`}
        />
        <span className="font-medium text-hs-text">
          {statusLabel(connected, isRunning)}
        </span>
        {health?.last_snapshot_ms != null && (
          <span>Last snapshot {timeAgo(health.last_snapshot_ms)}</span>
        )}
        <button
          onClick={() => setShowLogs(true)}
          className="text-hs-grey underline decoration-dotted underline-offset-2 transition-colors hover:text-hs-text"
          title="Open backend log viewer"
        >
          View logs
        </button>
        {hasErrors && (
          <span
            className="rounded border border-hs-red/30 bg-hs-red/10 px-2 py-0.5 text-xs text-hs-red"
            title="Active engine/runtime issues"
          >
            {errorCount} error(s)
          </span>
        )}
      </div>

      {showLogs && <LogModal onClose={() => setShowLogs(false)} />}
    </>
  );
}
