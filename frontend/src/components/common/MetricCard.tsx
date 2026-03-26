interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  valueColor?: string;
}

export function MetricCard({ label, value, sub, valueColor }: MetricCardProps) {
  return (
    <div className="bg-[#141a22] rounded-lg p-4 border border-[#2a2d35]">
      <p className="text-[#4a4e69] text-xs uppercase tracking-wider mb-1">
        {label}
      </p>
      <p
        className="text-xl font-semibold truncate"
        style={{ color: valueColor ?? "#fafafa" }}
      >
        {value}
      </p>
      {sub && <p className="text-[#4a4e69] text-xs mt-1">{sub}</p>}
    </div>
  );
}
