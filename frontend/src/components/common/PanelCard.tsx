import type { ReactNode } from "react";

interface PanelCardProps {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  dense?: boolean;
}

/**
 * Standard surface card used throughout the dashboard.
 *
 * Replaces the repeated pattern:
 *   <div className="bg-hs-surface border border-hs-grid rounded-2xl p-4">
 *     <h2 className="text-hs-text font-medium mb-3">{title}</h2>
 *     ...
 *   </div>
 */
export function PanelCard({
  title,
  action,
  children,
  className,
  bodyClassName,
  dense = false,
}: Readonly<PanelCardProps>) {
  const padding = dense ? "p-3" : "p-4";
  return (
    <div
      className={`bg-hs-surface border border-hs-grid rounded-2xl ${padding} ${
        className ?? ""
      }`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h2 className="text-hs-text font-medium">{title}</h2>}
          {action}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </div>
  );
}
