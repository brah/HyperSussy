import { useEffect, useRef, useState } from "react";

/**
 * Measures a container's pixel width via ResizeObserver.
 *
 * ResizeObserver delivers contentRect.width asynchronously after the browser
 * has already performed layout — no forced synchronous layout reads. This is
 * important when several charts mount simultaneously: a synchronous read per
 * chart (e.g. getBoundingClientRect) would chain N forced reflows before the
 * first paint, which was the original ResponsiveContainer problem.
 *
 * LCP note: charts render nothing until the first ResizeObserver callback
 * (~1 frame). In practice this is imperceptible because charts also wait for
 * API data; LCP on a chart-heavy page is bound by data fetch latency, not the
 * ~16 ms ResizeObserver delay.
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
