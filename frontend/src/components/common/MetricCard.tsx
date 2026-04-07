import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value?: string;
  valueNode?: ReactNode;
  sub?: string;
  subNode?: ReactNode;
  valueClassName?: string;
  onClick?: () => void;
  compact?: boolean;
}

/**
 * Small KPI tile. Supports either a plain `value` string or a custom
 * `valueNode` for richer content. When `onClick` is provided the card
 * becomes a button.
 */
export function MetricCard({
  label,
  value,
  valueNode,
  sub,
  subNode,
  valueClassName,
  onClick,
  compact = false,
}: Readonly<MetricCardProps>) {
  const padding = compact ? "p-3" : "p-4";
  const valueSize = compact ? "text-base" : "text-xl";
  const interactive = onClick != null;
  const className = `rounded-2xl border border-hs-grid bg-hs-surface ${padding} text-left w-full ${
    interactive ? "wise-interactive cursor-pointer hover:border-hs-green" : ""
  }`;

  const content = (
    <>
      <p className="mb-1 text-xs uppercase tracking-wider text-hs-grey">
        {label}
      </p>
      {valueNode ?? (
        <p
          className={`truncate ${valueSize} font-semibold ${
            valueClassName ?? "text-hs-text"
          }`}
        >
          {value}
        </p>
      )}
      {subNode}
      {sub && !subNode && <p className="mt-1 text-xs text-hs-grey">{sub}</p>}
    </>
  );

  if (interactive) {
    return (
      <button type="button" onClick={onClick} className={className}>
        {content}
      </button>
    );
  }

  return <div className={className}>{content}</div>;
}
