import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useWsStore } from "../../api/websocket";
import { normalizeAddress, shortAddress } from "../../utils/format";
import { useWatchlistStore } from "../../stores/watchlistStore";

const NAV = [
  { to: "/", label: "Market" },
  { to: "/wallets", label: "Wallets" },
] as const;

export function Sidebar() {
  const connected = useWsStore((s) => s.connected);
  const health = useWsStore((s) => s.health);
  const watchlist = useWatchlistStore((s) => s.items);
  const removeWatched = useWatchlistStore((s) => s.remove);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const hasErrors =
    (health?.engine_errors.length ?? 0) + (health?.runtime_errors.length ?? 0) > 0;

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const addr = normalizeAddress(search.trim());
    if (addr) {
      navigate(`/wallets/${addr}`);
      setSearch("");
    }
  }

  const dotColor =
    connected && health?.is_running
      ? "bg-hs-teal"
      : connected && hasErrors
      ? "bg-hs-red"
      : connected
      ? "bg-hs-orange"
      : "bg-hs-red";

  const statusLabel = !connected
    ? "Offline"
    : !health
    ? "Connecting..."
    : health.is_running
    ? "Live"
    : "Stopped";

  return (
    <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-hs-grid bg-hs-bg">
      <div className="border-b border-hs-grid p-4">
        <span className="text-lg font-black tracking-tight text-hs-text">
          HyperSussy
        </span>
      </div>

      <nav className="space-y-1 p-3">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `block rounded-full px-4 py-2 text-sm transition-all wise-interactive ${
                isActive
                  ? "bg-hs-mint text-hs-green font-semibold"
                  : "text-hs-grey hover:bg-hs-mint/50 hover:text-hs-text"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1 min-h-0 overflow-y-auto border-t border-hs-grid px-3 py-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-hs-grey">
            Watchlist
          </span>
          {watchlist.length > 0 && (
            <span className="text-[10px] text-hs-grey">{watchlist.length}</span>
          )}
        </div>
        {watchlist.length === 0 ? (
          <p className="text-xs text-hs-grey/70 leading-snug">
            Star a coin or wallet to pin it here.
          </p>
        ) : (
          <ul className="space-y-1">
            {watchlist.map((it) => {
              const to =
                it.kind === "coin" ? `/?coin=${it.id}` : `/wallets/${it.id}`;
              const display =
                it.kind === "coin"
                  ? it.id
                  : (it.label ?? shortAddress(it.id));
              return (
                <li
                  key={`${it.kind}:${it.id}`}
                  className="group flex items-center gap-1"
                >
                  <button
                    onClick={() => navigate(to)}
                    className="flex-1 flex items-center gap-2 rounded-md px-2 py-1 text-left text-xs text-hs-text transition-colors hover:bg-hs-mint/40"
                  >
                    <span className="inline-flex w-7 justify-center text-[9px] font-semibold uppercase tracking-wide text-hs-grey">
                      {it.kind === "coin" ? "COIN" : "WAL"}
                    </span>
                    <span className="truncate font-mono">{display}</span>
                  </button>
                  <button
                    onClick={() => removeWatched(it.kind, it.id)}
                    title="Remove from watchlist"
                    className="opacity-0 group-hover:opacity-100 px-1 text-xs text-hs-grey transition-opacity hover:text-hs-red"
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-hs-grid p-3">
        <form onSubmit={handleSearch}>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="0x wallet..."
            className="w-full rounded-[10px] border border-hs-grid bg-hs-bg px-2 py-1.5 text-xs text-hs-text
                       placeholder-hs-grey focus:border-hs-green focus:outline-none"
          />
        </form>
        <div className="mt-3 flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${dotColor}`} />
          <span className="text-xs text-hs-grey">{statusLabel}</span>
        </div>
      </div>
    </aside>
  );
}
