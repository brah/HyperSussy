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
      ? "bg-[#00d4aa]"
      : connected && hasErrors
      ? "bg-[#ff4b4b]"
      : connected
      ? "bg-[#ffa500]"
      : "bg-[#ff4b4b]";

  const statusLabel = !connected
    ? "Offline"
    : !health
    ? "Connecting..."
    : health.is_running
    ? "Live"
    : "Stopped";

  return (
    <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-[#2a2d35] bg-[#141a22]">
      <div className="border-b border-[#2a2d35] p-4">
        <span className="text-lg font-bold tracking-tight text-[#fafafa]">
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
              `block rounded px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-[#00d4aa]/10 text-[#00d4aa]"
                  : "text-[#4a4e69] hover:bg-[#0e1117] hover:text-[#fafafa]"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-[#2a2d35] p-3">
        <form onSubmit={handleSearch}>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="0x wallet..."
            className="w-full rounded border border-[#2a2d35] bg-[#0e1117] px-2 py-1.5 text-xs text-[#fafafa]
                       placeholder-[#4a4e69] focus:border-[#00d4aa] focus:outline-none"
          />
        </form>
        <div className="mt-3 flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${dotColor}`} />
          <span className="text-xs text-[#4a4e69]">{statusLabel}</span>
        </div>
      </div>
    </aside>
  );
}
