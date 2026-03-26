import { usePanelStore } from "../../stores/panelStore";

interface PanelDef {
  key: string;
  label: string;
  defaultVisible?: boolean;
}

interface PanelToggleBarProps {
  panels: PanelDef[];
}

/**
 * Horizontal row of pill toggle buttons that show/hide named panels.
 * Teal background = visible; grey = hidden.
 */
export function PanelToggleBar({ panels }: Readonly<PanelToggleBarProps>) {
  const toggle = usePanelStore((s) => s.toggle);
  const isVisible = usePanelStore((s) => s.isVisible);

  return (
    <div className="flex flex-wrap gap-1.5">
      {panels.map(({ key, label, defaultVisible = true }) => {
        const visible = isVisible(key, defaultVisible);
        return (
          <button
            key={key}
            onClick={() => toggle(key)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              visible
                ? "bg-hs-green/20 text-hs-green border border-hs-green/40"
                : "bg-hs-surface text-hs-grey border border-hs-grid hover:text-hs-text"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
