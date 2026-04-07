import { memo } from "react";
import { usePanelStore, usePanelVisible } from "../../stores/panelStore";

interface PanelDef {
  key: string;
  label: string;
  defaultVisible?: boolean;
}

interface PanelToggleBarProps {
  panels: PanelDef[];
}

/** Single pill — subscribes only to its own panel key. */
const TogglePill = memo(function TogglePill({
  panelKey,
  label,
  defaultVisible = true,
}: Readonly<{ panelKey: string; label: string; defaultVisible?: boolean }>) {
  const visible = usePanelVisible(panelKey, defaultVisible);
  const toggle = usePanelStore((s) => s.toggle);

  return (
    <button
      onClick={() => toggle(panelKey, defaultVisible)}
      className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all wise-interactive ${
        visible
          ? "bg-hs-mint text-hs-green border border-hs-green"
          : "bg-hs-surface text-hs-grey border border-hs-grid hover:text-hs-text"
      }`}
    >
      {label}
    </button>
  );
});

/**
 * Horizontal row of pill toggle buttons that show/hide named panels.
 * Each pill subscribes independently so toggling one doesn't re-render others.
 */
export const PanelToggleBar = memo(function PanelToggleBar({
  panels,
}: Readonly<PanelToggleBarProps>) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {panels.map(({ key, label, defaultVisible }) => (
        <TogglePill
          key={key}
          panelKey={key}
          label={label}
          defaultVisible={defaultVisible}
        />
      ))}
    </div>
  );
});
