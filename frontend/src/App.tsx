import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/layout/Sidebar";
import { OverviewPage } from "./pages/OverviewPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ChartsPage } from "./pages/ChartsPage";
import { KlinesPage } from "./pages/KlinesPage";
import { WalletDetailPage } from "./pages/WalletDetailPage";
import { WhaleTrackerPage } from "./pages/WhaleTrackerPage";
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
          <Route path="/" element={<OverviewPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/charts" element={<ChartsPage />} />
          <Route path="/klines" element={<KlinesPage />} />
          <Route path="/wallet/:address" element={<WalletDetailPage />} />
          <Route path="/whales" element={<WhaleTrackerPage />} />
        </Routes>
      </main>
    </div>
  );
}
