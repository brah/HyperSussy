import { NavLink, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useWsStore } from "../../api/websocket";
import { normalizeAddress } from "../../utils/format";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/alerts", label: "Alerts" },
  { to: "/charts", label: "Charts" },
  { to: "/klines", label: "Klines" },
  { to: "/whales", label: "Whale Tracker" },
] as const;

export function Sidebar() {
  const connected = useWsStore((s) => s.connected);
  const health = useWsStore((s) => s.health);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const addr = normalizeAddress(search.trim());
    if (addr) {
      navigate(`/wallet/${addr}`);
      setSearch("");
    }
  }

  const dotColor =
    connected && health?.is_running
      ? "bg-[#00d4aa]"
      : connected
      ? "bg-[#ffa500]"
      : "bg-[#ff4b4b]";

  return (
    <aside className="w-52 shrink-0 flex flex-col bg-[#141a22] border-r border-[#2a2d35] h-screen sticky top-0">
      <div className="p-4 border-b border-[#2a2d35]">
        <span className="text-[#fafafa] font-bold text-lg tracking-tight">
          HyperSussy
        </span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `block px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? "bg-[#00d4aa]/10 text-[#00d4aa]"
                  : "text-[#4a4e69] hover:text-[#fafafa] hover:bg-[#0e1117]"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-3 border-t border-[#2a2d35]">
        <form onSubmit={handleSearch}>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="0x wallet..."
            className="w-full bg-[#0e1117] border border-[#2a2d35] text-[#fafafa]
                       text-xs rounded px-2 py-1.5 placeholder-[#4a4e69]
                       focus:outline-none focus:border-[#00d4aa]"
          />
        </form>
        <div className="flex items-center gap-2 mt-3">
          <span className={`w-2 h-2 rounded-full ${dotColor}`} />
          <span className="text-[#4a4e69] text-xs">
            {connected ? (health?.is_running ? "Live" : "Connecting…") : "Offline"}
          </span>
        </div>
      </div>
    </aside>
  );
}
