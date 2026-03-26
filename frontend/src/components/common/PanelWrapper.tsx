import { usePanelStore } from "../../stores/panelStore";

interface PanelWrapperProps {
  panelKey: string;
  defaultVisible?: boolean;
  children: React.ReactNode;
}

/** Renders children only when the named panel is toggled on. */
export function PanelWrapper({
  panelKey,
  defaultVisible = true,
  children,
}: Readonly<PanelWrapperProps>) {
  const isVisible = usePanelStore((s) => s.isVisible(panelKey, defaultVisible));
  return isVisible ? <>{children}</> : null;
}
