import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import { useWsStore } from "../../api/websocket";
import { formatPrice, formatUSD } from "../../utils/format";

const ALL = "All";

interface CoinSelectorProps {
  coins: string[];
  value: string;
  onChange: (coin: string) => void;
}

/**
 * Autocomplete coin picker.
 *
 * - Typing filters the coin list; first match ghost-completes inline.
 * - Arrow keys / Enter / Escape / Tab for keyboard nav.
 * - Each result row shows live mark price + OI from the WS store.
 * - Selecting "All" (or clearing input) returns to overview mode.
 */
export const CoinSelector = memo(function CoinSelector({
  coins,
  value,
  onChange,
}: Readonly<CoinSelectorProps>) {
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const [query, setQuery] = useState(value === ALL ? "" : value);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  // Keep query in sync when external value changes (e.g. browser back).
  useEffect(() => {
    setQuery(value === ALL ? "" : value);
  }, [value]);

  const snapshots = useWsStore((s) => s.snapshots);

  // Coins excluding "All" — that sentinel is handled separately.
  const coinList = useMemo(() => coins.filter((c) => c !== ALL), [coins]);

  // Default order: descending OI. Untracked coins (no snapshot yet) sink to bottom.
  const byOI = useMemo(
    () =>
      [...coinList].sort((a, b) => {
        const aOI = snapshots[a]?.open_interest_usd ?? -1;
        const bOI = snapshots[b]?.open_interest_usd ?? -1;
        return bOI - aOI;
      }),
    [coinList, snapshots],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q) return byOI;
    // When searching, keep OI order but restrict to matches.
    return byOI.filter((c) => c.toUpperCase().includes(q));
  }, [byOI, query]);

  // Ghost (inline autocomplete) text: the remaining suffix of the first match.
  const ghost = useMemo(() => {
    const q = query.trim();
    if (!q || filtered.length === 0) return "";
    const first = filtered[0];
    if (first.toUpperCase().startsWith(q.toUpperCase())) {
      return first.slice(q.length);
    }
    return "";
  }, [query, filtered]);

  // Reset active index only when the user's query changes, not on every WS push.
  // WS updates change `byOI`/`filtered` references but keep the same coins in
  // the same relative order — resetting on those would jump the cursor to the
  // top mid-navigation.
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  // Scroll the active item into view.
  useEffect(() => {
    if (!open) return;
    const li = listRef.current?.children[activeIdx] as HTMLElement | undefined;
    li?.scrollIntoView({ block: "nearest" });
  }, [activeIdx, open]);

  function commit(coin: string) {
    setOpen(false);
    setQuery(coin === ALL ? "" : coin);
    onChange(coin);
    inputRef.current?.blur();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        setOpen(true);
        return;
      }
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (filtered.length > 0) commit(filtered[activeIdx]);
        break;
      case "Tab":
        // Accept ghost completion.
        if (ghost && open) {
          e.preventDefault();
          commit(filtered[0]);
        }
        break;
      case "Escape":
        setOpen(false);
        setQuery(value === ALL ? "" : value);
        break;
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    setOpen(true);
  }

  function handleFocus() {
    setOpen(true);
    setActiveIdx(0);
  }

  function handleBlur(e: React.FocusEvent) {
    // Only close if focus left the whole widget (not moving to the list).
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setOpen(false);
      // Snap back to current value if input was left mid-query.
      setQuery(value === ALL ? "" : value);
    }
  }

  const isLoading = coins.length === 0;

  return (
    <div className="relative" onBlur={handleBlur}>
      {/* Input with ghost overlay */}
      <div className="relative">
        {/* Ghost text — sits behind the real input */}
        {ghost && open && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 flex items-center px-3 text-sm font-mono"
          >
            <span className="invisible">{query}</span>
            <span className="text-hs-grey/50">{ghost}</span>
          </div>
        )}
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open && filtered.length > 0 ? `${listboxId}-${activeIdx}` : undefined}
          value={query}
          onChange={handleChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          placeholder={isLoading ? "Loading…" : "Search coin…"}
          className="w-44 rounded-[10px] border border-hs-grid bg-hs-surface px-3 py-1.5
                     text-sm text-hs-text font-mono placeholder-hs-grey
                     focus:border-hs-green focus:outline-none
                     disabled:cursor-not-allowed disabled:text-hs-grey"
        />
        {/* Clear button — shows when a coin is selected */}
        {value !== ALL && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => commit(ALL)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-hs-grey hover:text-hs-text text-xs leading-none"
            aria-label="Clear selection"
          >
            ×
          </button>
        )}
      </div>

      {/* Dropdown */}
      {open && filtered.length > 0 && (
        <ul
          id={listboxId}
          ref={listRef}
          role="listbox"
          className="absolute z-50 mt-1 w-72 max-h-72 overflow-y-auto
                     rounded-xl border border-hs-grid bg-hs-surface shadow-lg"
        >
          {filtered.map((coin, i) => {
            const snap = snapshots[coin];
            const isActive = i === activeIdx;
            return (
              <li
                key={coin}
                id={`${listboxId}-${i}`}
                role="option"
                aria-selected={isActive}
                onMouseDown={(e) => { e.preventDefault(); commit(coin); }}
                onMouseEnter={() => setActiveIdx(i)}
                className={`flex items-center justify-between px-3 py-2 cursor-pointer text-sm transition-colors ${
                  isActive ? "bg-hs-mint text-hs-text" : "hover:bg-hs-grid/50"
                }`}
              >
                <span className="font-mono font-semibold text-hs-green">{coin}</span>
                {snap ? (
                  <span className="flex items-center gap-3 text-xs text-hs-grey tabular-nums">
                    <span>{formatPrice(snap.mark_price)}</span>
                    <span className="text-hs-secondary">{formatUSD(snap.open_interest_usd)} OI</span>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {/* No results */}
      {open && query.trim() && filtered.length === 0 && (
        <div className="absolute z-50 mt-1 w-72 rounded-xl border border-hs-grid bg-hs-surface px-3 py-3 text-sm text-hs-grey">
          No coins match "{query}"
        </div>
      )}
    </div>
  );
});
