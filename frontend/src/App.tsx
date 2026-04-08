import { lazy, Suspense, useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/layout/Sidebar";
import { MarketPage } from "./pages/MarketPage";
import { WalletsPage } from "./pages/WalletsPage";
import { startWebSocket, stopWebSocket } from "./api/websocket";

// Config page is lazy-loaded: it's rarely opened and would
// otherwise inflate the initial bundle with form-heavy code that
// most sessions never touch.
const ConfigPage = lazy(() =>
  import("./pages/ConfigPage").then((m) => ({ default: m.ConfigPage })),
);

export function App() {
  useEffect(() => {
    startWebSocket();
    return () => stopWebSocket();
  }, []);

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 bg-hs-bg min-w-0">
        <Routes>
          <Route path="/" element={<MarketPage />} />
          <Route path="/wallets" element={<WalletsPage />} />
          <Route path="/wallets/:address" element={<WalletsPage />} />
          <Route
            path="/config"
            element={
              <Suspense
                fallback={
                  <div className="text-hs-grey text-sm">Loading config…</div>
                }
              >
                <ConfigPage />
              </Suspense>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
