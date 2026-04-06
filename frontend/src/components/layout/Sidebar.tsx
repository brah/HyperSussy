import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useWsStore } from "../../api/websocket";
import { normalizeAddress } from "../../utils/format";

const NAV = [
  { to: "/", label: "Market" },
  { to: "/wallets", label: "Wallets" },
] as const;

export function Sidebar() {
  const connected = useWsStore((s) => s.connected);
  const health = useWsStore((s) => s.health);
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
    <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-hs-grid bg-white">
      <div className="border-b border-hs-grid p-4">
        <span className="text-lg font-black tracking-tight text-hs-text">
          HyperSussy
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `block rounded-full px-4 py-2 text-sm transition-all wise-interactive ${
                isActive
                  ? "bg-hs-mint text-hs-green-dark font-semibold"
                  : "text-hs-grey hover:bg-[rgba(211,242,192,0.4)] hover:text-hs-text"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

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
