import { useEffect, useRef, useState } from "react";

/**
 * Measures a container's pixel width via ResizeObserver.
 *
 * Unlike recharts' ResponsiveContainer (which calls getBoundingClientRect()
 * synchronously on mount and forces a layout read), ResizeObserver delivers
 * dimensions asynchronously after the browser has already performed layout.
 * This avoids the layout-thrashing pattern that occurs when several charts
 * mount simultaneously and each one forces a synchronous reflow.
 *
 * Usage:
 *   const [ref, width] = useContainerWidth();
 *   return (
 *     <div ref={ref} style={{ width: "100%" }}>
 *       {width > 0 && <MyChart width={width} height={height} />}
 *     </div>
 *   );
 */
export function useContainerWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w !== undefined) setWidth(Math.floor(w));
    });

    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, width];
}
