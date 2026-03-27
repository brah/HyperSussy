import { useEffect, useRef, useState } from "react";
import { fetchLogs } from "../../api/client";

interface LogModalProps {
  onClose: () => void;
}

/** Full-screen terminal-style modal that streams the backend log file. */
export function LogModal({ onClose }: Readonly<LogModalProps>) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchLogs(500)
      .then((text) => setContent(text))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err))
      );
  }, []);

  // Scroll to bottom once content loads
  useEffect(() => {
    if (content !== null) {
      bottomRef.current?.scrollIntoView();
    }
  }, [content]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="relative flex flex-col w-full max-w-5xl h-[80vh] bg-hs-bg border border-hs-grid rounded-lg overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title bar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-hs-grid shrink-0">
          <span className="font-mono text-xs text-hs-grey">
            hypersussy-dashboard.log — last 500 lines
          </span>
          <button
            onClick={onClose}
            className="text-hs-grey hover:text-hs-text text-lg leading-none px-1"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Log content */}
        <div className="flex-1 overflow-y-auto p-4">
          {error !== null ? (
            <p className="font-mono text-xs text-hs-red">{error}</p>
          ) : content === null ? (
            <p className="font-mono text-xs text-hs-grey animate-pulse">
              Loading…
            </p>
          ) : (
            <pre className="font-mono text-xs text-hs-text whitespace-pre-wrap break-all leading-5">
              {content}
            </pre>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
