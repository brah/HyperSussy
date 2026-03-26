/** Time formatting helpers. */

/** Format a Unix-ms timestamp as a locale date-time string. */
export function fmtDatetime(ms: number): string {
  return new Date(ms).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Format a Unix-ms timestamp as HH:MM. */
export function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Convert Unix-ms to Unix-seconds (for Lightweight Charts). */
export function msToSec(ms: number): number {
  return Math.floor(ms / 1000);
}

/** Format relative time (e.g. "3 min ago"). */
export function timeAgo(ms: number): string {
  const diffS = Math.floor((Date.now() - ms) / 1000);
  if (diffS < 60) return `${diffS}s ago`;
  if (diffS < 3600) return `${Math.floor(diffS / 60)}m ago`;
  if (diffS < 86400) return `${Math.floor(diffS / 3600)}h ago`;
  return `${Math.floor(diffS / 86400)}d ago`;
}
