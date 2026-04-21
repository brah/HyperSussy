import { useEffect, type DependencyList, type RefObject } from "react";
import { createChart, type DeepPartial, type ChartOptions, type IChartApi } from "lightweight-charts";
import { lwcChartOptions } from "../theme/chartDefaults";

/**
 * Boilerplate for a lightweight-charts panel chart.
 *
 * Several small charts (OI, Funding, Mark/Oracle, TradeFlow) share
 * the same shape: create chart → add series + setData → fit scale →
 * return remove(). Running the shared cleanup through one helper
 * keeps the per-chart component focused on its actual series setup
 * and makes sure every chart correctly tears itself down on unmount
 * or on dependency changes.
 *
 * The chart is (re)created whenever ``width``, ``height``, or any
 * entry in ``deps`` changes. Gate on ``width > 0`` and any data
 * emptiness checks in the caller before they reach this hook.
 *
 * Args:
 *   containerRef: div the chart mounts into.
 *   width: measured container width (0 skips creation).
 *   height: fixed chart height.
 *   setup: callback that receives the live ``IChartApi`` and
 *     configures its series. Anything returned is ignored; the
 *     chart's ``remove()`` cleanup runs unconditionally.
 *   deps: additional deps that should retrigger chart recreation
 *     (e.g. the data array reference, label strings).
 *   optionsOverrides: merged over :func:`lwcChartOptions` at create
 *     time. Pass ``{leftPriceScale: {visible: false}}`` etc. here
 *     rather than reaching into the chart after the fact.
 */
export function useLightweightChart(
  containerRef: RefObject<HTMLDivElement | null>,
  width: number,
  height: number,
  setup: (chart: IChartApi) => void,
  deps: DependencyList,
  optionsOverrides?: DeepPartial<ChartOptions>,
): void {
  useEffect(() => {
    const el = containerRef.current;
    if (!el || width === 0) return;

    const chart = createChart(el, {
      ...lwcChartOptions(width, height),
      ...optionsOverrides,
    });
    setup(chart);
    chart.timeScale().fitContent();
    return () => chart.remove();
    // ``setup`` and ``optionsOverrides`` are read but deliberately
    // omitted from the dep list — callers pass inline closures and
    // object literals, so including them would rebuild the chart
    // on every parent render. Data deps must be threaded through
    // ``deps``.
  }, [width, height, ...deps]);
}
