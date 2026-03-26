import { usePanelVisible } from "../../stores/panelStore";

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
  const visible = usePanelVisible(panelKey, defaultVisible);
  return visible ? <>{children}</> : null;
}
