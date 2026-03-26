export const INTERVAL_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
export type Interval = (typeof INTERVAL_OPTIONS)[number];

interface IntervalSelectorProps {
  value: Interval;
  onChange: (v: Interval) => void;
}

/** Button group for candle interval selection. */
export function IntervalSelector({
  value,
  onChange,
}: Readonly<IntervalSelectorProps>) {
  return (
    <div className="flex rounded border border-hs-grid overflow-hidden">
      {INTERVAL_OPTIONS.map((iv) => (
        <button
          key={iv}
          onClick={() => onChange(iv)}
          className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
            value === iv
              ? "bg-hs-green text-hs-bg"
              : "bg-hs-surface text-hs-grey hover:text-hs-text hover:bg-hs-bg"
          }`}
        >
          {iv}
        </button>
      ))}
    </div>
  );
}
