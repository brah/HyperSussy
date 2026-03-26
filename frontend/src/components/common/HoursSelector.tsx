const HOUR_OPTIONS = [6, 12, 24, 48, 72] as const;
export type Hours = (typeof HOUR_OPTIONS)[number];

interface HoursSelectorProps {
  value: Hours;
  onChange: (v: Hours) => void;
}

/** Button group for lookback hours selection (6h–72h). */
export function HoursSelector({
  value,
  onChange,
}: Readonly<HoursSelectorProps>) {
  return (
    <div className="flex rounded border border-hs-grid overflow-hidden">
      {HOUR_OPTIONS.map((h) => (
        <button
          key={h}
          onClick={() => onChange(h)}
          className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
            value === h
              ? "bg-hs-green text-hs-bg"
              : "bg-hs-surface text-hs-grey hover:text-hs-text hover:bg-hs-bg"
          }`}
        >
          {h}h
        </button>
      ))}
    </div>
  );
}
