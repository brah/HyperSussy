import {
  useIsWatched,
  useWatchlistStore,
  type WatchlistKind,
} from "../../stores/watchlistStore";

interface WatchStarProps {
  kind: WatchlistKind;
  id: string;
  label?: string;
  size?: "sm" | "md";
}

/** Star/unstar toggle for adding a coin or wallet to the sidebar watchlist. */
export function WatchStar({
  kind,
  id,
  label,
  size = "md",
}: Readonly<WatchStarProps>) {
  const watched = useIsWatched(kind, id);
  const toggle = useWatchlistStore((s) => s.toggle);

  const px = size === "sm" ? 14 : 18;

  return (
    <button
      type="button"
      onClick={() => toggle(kind, id, label)}
      title={watched ? "Remove from watchlist" : "Add to watchlist"}
      aria-pressed={watched}
      className={`inline-flex items-center justify-center rounded-full transition-colors ${
        watched
          ? "text-hs-orange hover:text-hs-orange/80"
          : "text-hs-grey hover:text-hs-orange"
      }`}
    >
      <svg
        width={px}
        height={px}
        viewBox="0 0 24 24"
        fill={watched ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth={2}
        strokeLinejoin="round"
      >
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    </button>
  );
}
