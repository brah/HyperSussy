interface CoinSelectorProps {
  coins: string[];
  value: string;
  onChange: (coin: string) => void;
}

export function CoinSelector({ coins, value, onChange }: CoinSelectorProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-[#141a22] border border-[#2a2d35] text-[#fafafa] text-sm
                 rounded px-3 py-1.5 focus:outline-none focus:border-[#00d4aa]"
    >
      {coins.length === 0 && (
        <option value="" disabled>
          Loading…
        </option>
      )}
      {coins.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}
