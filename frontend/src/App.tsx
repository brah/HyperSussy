import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/layout/Sidebar";
import { MarketPage } from "./pages/MarketPage";
import { WalletsPage } from "./pages/WalletsPage";
import { startWebSocket, stopWebSocket } from "./api/websocket";

export function App() {
  useEffect(() => {
    startWebSocket();
    return () => stopWebSocket();
  }, []);

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 bg-[#0e1117] min-w-0">
        <Routes>
          <Route path="/" element={<MarketPage />} />
          <Route path="/wallets" element={<WalletsPage />} />
          <Route path="/wallets/:address" element={<WalletsPage />} />
        </Routes>
      </main>
    </div>
  );
}
