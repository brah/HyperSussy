import { useEffect, useMemo, useRef, useState } from "react";
import { fetchLogs } from "../../api/client";

interface LogModalProps {
  onClose: () => void;
}

const REFRESH_MS = 5_000;
const LINE_OPTIONS = [200, 500, 1000, 2000] as const;
const ANSI_PATTERN = new RegExp(
  // Build escape char at runtime to keep eslint happy with no-control-regex.
  `${String.fromCharCode(27)}\\[[0-9;?]*[ -/]*[@-~]`,
  "g"
);

function stripAnsi(text: string): string {
  return text.replace(ANSI_PATTERN, "");
}

function lineTone(line: string): string {
  const normalized = line.toLowerCase();
  if (
    normalized.includes("[error") ||
    normalized.includes(" error ") ||
    normalized.includes("traceback") ||
    normalized.includes("exception")
  ) {
    return "text-red-300";
  }
  if (
    normalized.includes("[warning") ||
    normalized.includes(" warning ") ||
    normalized.includes("rate-limited") ||
    normalized.includes("429")
  ) {
    return "text-amber-200";
  }
  if (normalized.includes("[info") || normalized.includes(" info ")) {
    return "text-emerald-200";
  }
  if (normalized.includes("[debug") || normalized.includes(" debug ")) {
    return "text-slate-400";
  }
  return "text-gray-300";
}

/** Full-screen terminal-style modal that streams the backend log file. */
export function LogModal({ onClose }: Readonly<LogModalProps>) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<(typeof LINE_OPTIONS)[number]>(500);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const text = await fetchLogs(lines);
        if (cancelled) return;
        setContent(text);
        setError(null);
      } catch (err: unknown) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    void load();
    if (!autoRefresh) {
      return () => {
        cancelled = true;
      };
    }

    const timer = window.setInterval(() => {
      void load();
    }, REFRESH_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [autoRefresh, lines, refreshNonce]);

  useEffect(() => {
    if (content !== null) {
      bottomRef.current?.scrollIntoView({ block: "end" });
    }
  }, [content]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const displayLines = useMemo(() => {
    if (!content) return [];
    return stripAnsi(content)
      .split(/\r?\n/)
      .filter((line) => line.length > 0);
  }, [content]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="relative flex h-[82vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-[#2a2d35] bg-[#0e0f0c]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2a2d35] px-4 py-3 shrink-0">
          <div className="flex flex-col">
            <span className="font-mono text-xs text-gray-400">
              hypersussy-dashboard.log
            </span>
            <span className="text-xs text-gray-400">
              Always available. Auto-refreshes every 5s while open.
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 rounded border border-[#2a2d35] bg-[#141a22] px-2 py-1 text-xs text-gray-400">
              <span>Lines</span>
              <select
                value={lines}
                onChange={(e) => setLines(Number(e.target.value) as typeof lines)}
                className="bg-transparent text-gray-200 outline-none"
              >
                {LINE_OPTIONS.map((option) => (
                  <option key={option} value={option} className="bg-[#141a22]">
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <button
              onClick={() => setAutoRefresh((value) => !value)}
              className={`rounded border px-2 py-1 text-xs transition-colors ${
                autoRefresh
                  ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
                  : "border-[#2a2d35] bg-[#141a22] text-gray-400 hover:text-gray-200"
              }`}
            >
              {autoRefresh ? "Auto Refresh On" : "Auto Refresh Off"}
            </button>

            <button
              onClick={() => setRefreshNonce((value) => value + 1)}
              className="rounded border border-[#2a2d35] bg-[#141a22] px-2 py-1 text-xs text-gray-400 transition-colors hover:text-gray-200"
            >
              Refresh
            </button>

            <button
              onClick={onClose}
              className="px-1 text-lg leading-none text-gray-400 hover:text-gray-200"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4 border-b border-[#2a2d35] bg-[#141a22]/50 px-4 py-2 text-[11px] text-gray-400 shrink-0">
          <span className="text-emerald-200">INFO</span>
          <span className="text-amber-200">WARNING</span>
          <span className="text-red-300">ERROR</span>
          <span className="text-slate-400">DEBUG</span>
          <span>{displayLines.length} visible line(s)</span>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error !== null ? (
            <p className="font-mono text-xs text-red-400">{error}</p>
          ) : content === null ? (
            <p className="font-mono text-xs text-gray-400 animate-pulse">
              Loading...
            </p>
          ) : displayLines.length === 0 ? (
            <p className="font-mono text-xs text-gray-400">
              Log file is currently empty.
            </p>
          ) : (
            <div className="space-y-1">
              {displayLines.map((line, index) => (
                <div
                  key={`${index}-${line.slice(0, 24)}`}
                  className={
                    `font-mono text-xs whitespace-pre-wrap break-all leading-5 ` +
                    lineTone(line)
                  }
                >
                  {line}
                </div>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
