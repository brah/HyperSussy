import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useWsStore } from "../api/websocket";
import { normalizeAddress } from "../utils/format";
import { AddWhaleForm } from "../components/whales/AddWhaleForm";
import { EmptyState } from "../components/common/EmptyState";
import { StatusBanner } from "../components/common/StatusBanner";
import { PageHeader } from "../components/layout/PageHeader";
import { PanelToggleBar } from "../components/common/PanelToggleBar";
import { PanelWrapper } from "../components/common/PanelWrapper";
import { WalletDetail } from "../components/wallets/WalletDetail";
import { WhaleListTable } from "../components/wallets/WhaleListTable";

const WALLET_PANELS = [
  { key: "add-whale-form", label: "Add Form" },
  { key: "whale-list", label: "List" },
  { key: "wallet-positions", label: "Positions" },
  { key: "wallet-trades", label: "Trades" },
  { key: "wallet-alerts", label: "Alerts" },
];

export function WalletsPage() {
  const { address: routeAddress = "" } = useParams<{ address: string }>();
  const navigate = useNavigate();
  const health = useWsStore((s) => s.health);
  const connected = useWsStore((s) => s.connected);
  const [selected, setSelected] = useState(routeAddress);
  const [searchInput, setSearchInput] = useState("");

  // Sync route param -> state when navigating directly to /wallets/:address
  useEffect(() => {
    setSelected(routeAddress);
  }, [routeAddress]);

  const handleSelect = (addr: string) => {
    setSelected(addr);
    navigate(`/wallets/${addr}`, { replace: true });
  };

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const addr = normalizeAddress(searchInput.trim());
    if (addr) {
      setSearchInput("");
      handleSelect(addr);
    }
  }

  return (
    <div>
      <PageHeader title="Wallets">
        <StatusBanner health={health} connected={connected} />
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="0x address..."
            className="bg-hs-surface border border-hs-grid text-hs-text text-sm
                       rounded-[10px] px-3 py-1.5 placeholder-hs-grey
                       focus:outline-none focus:border-hs-green w-56"
          />
          <button
            type="submit"
            className="px-3 py-1.5 text-sm rounded-full bg-hs-green text-hs-green-dark
                       font-semibold transition-all wise-interactive"
          >
            Go
          </button>
        </form>
        <PanelToggleBar panels={WALLET_PANELS} />
      </PageHeader>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* List column */}
        <div className="w-full lg:w-96 shrink-0 space-y-4">
          <PanelWrapper panelKey="add-whale-form">
            <AddWhaleForm />
          </PanelWrapper>

          <PanelWrapper panelKey="whale-list">
            <div className="bg-hs-surface border border-hs-grid rounded-2xl">
              <div className="border-b border-hs-grid px-4 py-3">
                <h2 className="text-hs-text font-medium">Tracked Addresses</h2>
              </div>
              <WhaleListTable
                selectedAddress={selected || null}
                onSelect={handleSelect}
              />
            </div>
          </PanelWrapper>
        </div>

        {/* Detail column */}
        <div className="flex-1 min-w-0">
          {!selected ? (
            <div className="bg-hs-surface border border-hs-grid rounded-2xl">
              <EmptyState message="Select a wallet from the list or search by address." />
            </div>
          ) : (
            <WalletDetail address={selected} />
          )}
        </div>
      </div>
    </div>
  );
}
