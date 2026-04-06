interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  valueClassName?: string;
}

export function MetricCard({
  label,
  value,
  sub,
  valueClassName,
}: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-hs-grid bg-hs-surface p-4">
      <p className="mb-1 text-xs uppercase tracking-wider text-hs-grey">
        {label}
      </p>
      <p className={`truncate text-xl font-semibold ${valueClassName ?? "text-hs-text"}`}>
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-hs-grey">{sub}</p>}
    </div>
  );
}
