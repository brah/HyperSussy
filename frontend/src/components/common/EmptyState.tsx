interface EmptyStateProps {
  message: string;
  state?: "empty" | "loading" | "error";
  error?: unknown;
  compact?: boolean;
}

/**
 * Centered placeholder for empty / loading / error states.
 *
 * - empty (default): muted grey text
 * - loading: muted grey with pulse animation
 * - error: red text, optionally appending the error message
 */
export function EmptyState({
  message,
  state = "empty",
  error,
  compact = false,
}: Readonly<EmptyStateProps>) {
  const sizing = compact ? "py-6" : "h-32 items-center";
  let tone: string;
  if (state === "error") {
    tone = "text-hs-red";
  } else if (state === "loading") {
    tone = "text-hs-grey animate-pulse";
  } else {
    tone = "text-hs-grey";
  }

  const text =
    state === "error" && error instanceof Error
      ? `${message}: ${error.message}`
      : message;

  return (
    <div
      className={`flex justify-center px-4 text-center text-sm ${sizing} ${tone}`}
    >
      {text}
    </div>
  );
}
