interface CoinSelectorProps {
  coins: string[];
  value: string;
  onChange: (coin: string) => void;
}

export function CoinSelector({ coins, value, onChange }: Readonly<CoinSelectorProps>) {
  const isLoading = coins.length === 0;

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={isLoading}
      className="rounded border border-hs-grid bg-hs-surface px-3 py-1.5 text-sm text-hs-text
                 focus:border-hs-green focus:outline-none disabled:cursor-not-allowed
                 disabled:text-hs-grey"
    >
      {isLoading && <option value={value}>Loading...</option>}
      {coins.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}
