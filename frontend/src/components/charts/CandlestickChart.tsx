import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createTextWatermark,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type IPaneApi,
  type ISeriesApi,
  type ITextWatermarkPluginApi,
  type LineData,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import type { CandleItem, OISnapshotItem, FundingSnapshotItem } from "../../api/types";
import {
  computeEMA,
  computeSMA,
  computeVWAP,
  EMA_50_COLOR,
  SMA_20_COLOR,
  SMA_7_COLOR,
  VWAP_COLOR,
  type IndicatorPoint,
} from "../../utils/indicators";
import { candleKey, useWsStore } from "../../api/websocket";
import { useIndicator } from "../../stores/indicatorStore";
import { chartDarkColors, colors } from "../../theme/colors";
import { msToSec } from "../../utils/time";
import { formatFundingRate, formatUSD } from "../../utils/format";

interface OverlayLine {
  key: string;
  data: IndicatorPoint[];
  color: string;
  lineWidth?: number;
  lineStyle?: LineStyle;
}

interface CandlestickChartProps {
  /**
   * Active coin and interval — used to subscribe to the matching
   * `lastCandles` slice in the WS store. The chart applies each
   * incoming bar via lightweight-charts' incremental ``update()``.
   */
  coin: string;
  interval: string;
  candles: CandleItem[];
  /**
   * True when ``candles`` is React Query's keepPreviousData placeholder
   * (i.e. it still belongs to the previous coin during a transition).
   * The chart skips live-patching the indicator math while this is set
   * so a new-coin WS bar can't corrupt SMA/EMA/VWAP computed against
   * the old-coin candles array.
   */
  isPlaceholderData?: boolean;
  height?: number;
  oiData?: OISnapshotItem[];
  showOI?: boolean;
  fundingData?: FundingSnapshotItem[];
  showFunding?: boolean;
  /**
   * Invoked when the user scrolls near the chart's left edge and
   * more historical bars should be fetched. Parent translates this
   * into a ``useInfiniteQuery.fetchNextPage()`` call. The chart
   * doesn't await — the resulting re-render with an extended
   * ``candles`` prop drives the series update.
   */
  onLoadOlder?: () => void;
  /** Whether older pages are available from the backend. */
  hasMoreOlder?: boolean;
  /** Whether an older-page fetch is currently in flight. */
  isLoadingOlder?: boolean;
}

// Trigger ``onLoadOlder`` when the visible logical range's ``from``
// comes within this many bars of the series start. 50 is enough
// runway that the new page typically lands before the user runs out
// of bars, while not being so large it triggers on every scroll.
const LOAD_OLDER_TRIGGER_BARS = 50;

// Pane layout: relative stretch factors (flex-grow style).
//   pane 0: candles            ── default pane created with the chart
//   pane 1: volume             ── always present
//   pane 2+: OI / Funding      ── added dynamically when toggled on.
// OI and Funding panes are stored by IPaneApi reference rather than
// numeric index because removing one would shift the other's index.
const PANE_INDEX_CANDLES = 0;
const PANE_INDEX_VOLUME = 1;
const STRETCH_CANDLES = 5;
const STRETCH_VOLUME = 1;
// OI and Funding sub-panes share the same stretch factor because they
// both want a bit more vertical real estate than volume but nowhere
// near the candle pane. If we ever want them to diverge, split into
// two constants again; today they would always track each other.
const STRETCH_SUB_PANE = 1.5;

const LEGEND_FONT_SIZE = 11;
const LEGEND_FONT_FAMILY = "ui-monospace, SFMono-Regular, monospace";
const LEGEND_COLOR = chartDarkColors.legend;

function legendLines(label: string, valueText: string) {
  return [
    {
      text: `${label} ${valueText}`,
      color: LEGEND_COLOR,
      fontSize: LEGEND_FONT_SIZE,
      fontFamily: LEGEND_FONT_FAMILY,
      fontStyle: "",
    },
  ];
}

const fundingPriceFormat = {
  type: "custom" as const,
  formatter: (v: number) => formatFundingRate(v),
  minMove: 0.000001,
};

/** Pull a numeric value from a series at the cursor, or fall back to the latest bar. */
function valueFromCrosshair(
  param: MouseEventParams<Time>,
  series: ISeriesApi<"Histogram"> | ISeriesApi<"Area"> | null,
): number | null {
  if (!series) return null;
  const point = param.seriesData.get(series) as { value?: number } | undefined;
  if (point?.value != null) return point.value;
  // Cursor outside chart — fall back to the most recent data point.
  const last = series.data().at(-1) as { value?: number } | undefined;
  return last?.value ?? null;
}

export const CandlestickChart = memo(function CandlestickChart({
  coin,
  interval,
  candles,
  isPlaceholderData = false,
  height = 400,
  oiData,
  showOI = false,
  fundingData,
  showFunding = false,
  onLoadOlder,
  hasMoreOlder = false,
  isLoadingOlder = false,
}: Readonly<CandlestickChartProps>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const volumePaneRef = useRef<IPaneApi<Time> | null>(null);
  const overlaySeriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const oiSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const oiPaneRef = useRef<IPaneApi<Time> | null>(null);
  const fundingSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fundingPaneRef = useRef<IPaneApi<Time> | null>(null);
  const volumeLegendRef = useRef<ITextWatermarkPluginApi<Time> | null>(null);
  const oiLegendRef = useRef<ITextWatermarkPluginApi<Time> | null>(null);
  const fundingLegendRef = useRef<ITextWatermarkPluginApi<Time> | null>(null);

  // Pane reorder controls. Holds one entry per moveable sub-pane
  // (anything below the candles pane), in current top-to-bottom order
  // with pixel `top`/`height` for absolute-positioning the up/down
  // buttons over the chart canvas. Recomputed whenever a pane is
  // added, removed, moved, or the container resizes.
  type PaneLayoutEntry = {
    key: "volume" | "oi" | "funding";
    label: string;
    paneIndex: number;
    top: number;
    height: number;
  };
  const [paneLayout, setPaneLayout] = useState<PaneLayoutEntry[]>([]);

  // rAF id of a scheduled-but-not-yet-run recompute. Used to coalesce
  // multiple recompute requests in the same frame and to defer the
  // actual measurement to the next frame, by which point LWC has
  // synced its internal pane widgets with the model. Calling
  // chart.paneSize(i) synchronously right after chart.addPane() can
  // throw "Value is undefined" because chart.panes() reads from the
  // model (already updated) while chart.paneSize() reads from the
  // pane widgets array (updated on the next layout pass).
  const recomputeRafRef = useRef<number>(0);

  const recomputePaneLayout = useCallback(() => {
    if (recomputeRafRef.current) return;
    recomputeRafRef.current = requestAnimationFrame(() => {
      recomputeRafRef.current = 0;
      const chart = chartRef.current;
      if (!chart) return;
      let panes;
      try {
        panes = chart.panes();
      } catch {
        return;
      }
      const entries: PaneLayoutEntry[] = [];
      let cumulativeTop = 0;
      for (let i = 0; i < panes.length; i++) {
        let size;
        try {
          size = chart.paneSize(i);
        } catch {
          // Pane widgets not yet in sync with the model — bail and
          // wait for the next trigger (mouseup/resize/crosshair) to
          // retry once the layout has settled.
          return;
        }
        // Skip pane 0 (candles) — it's pinned to the top.
        if (i > 0) {
          let key: PaneLayoutEntry["key"] | null = null;
          let label = "";
          if (panes[i] === volumePaneRef.current) {
            key = "volume";
            label = "VOL";
          } else if (panes[i] === oiPaneRef.current) {
            key = "oi";
            label = "OI";
          } else if (panes[i] === fundingPaneRef.current) {
            key = "funding";
            label = "FUND";
          }
          if (key) {
            entries.push({ key, label, paneIndex: i, top: cumulativeTop, height: size.height });
          }
        }
        // +1 px accounts for the separator line between panes.
        cumulativeTop += size.height + 1;
      }
      // Skip the React update if nothing actually moved/resized — this
      // function is called from the crosshair-move and mouseup handlers
      // and we don't want to trigger a re-render every pixel of motion.
      setPaneLayout((prev) => {
        if (
          prev.length === entries.length &&
          prev.every(
            (p, idx) =>
              p.key === entries[idx].key &&
              p.paneIndex === entries[idx].paneIndex &&
              p.top === entries[idx].top &&
              p.height === entries[idx].height,
          )
        ) {
          return prev;
        }
        return entries;
      });
    });
  }, []);

  const movePane = useCallback(
    (from: number, to: number) => {
      const chart = chartRef.current;
      if (!chart) return;
      const panes = chart.panes();
      // Pane 0 (candles) is pinned — never move anything into or out of slot 0.
      if (from < 1 || from >= panes.length) return;
      if (to < 1 || to >= panes.length) return;
      panes[from].moveTo(to);
      recomputePaneLayout();
    },
    [recomputePaneLayout],
  );

  // Stable holder so the chart-init useEffect (which runs once for
  // the lifetime of the chart) can call the latest recompute closure
  // without listing it as a dep — adding it would tear down and
  // recreate the chart on every render.
  const recomputePaneLayoutRef = useRef(recomputePaneLayout);
  recomputePaneLayoutRef.current = recomputePaneLayout;
  // The (coin, interval) key whose historical data the candle/volume
  // series currently holds. Live WS updates are only applied when
  // this matches the active props — otherwise a stray bar from a
  // mid-transition coin change could be appended to stale data.
  // Empty string = nothing seeded yet.
  const seededKeyRef = useRef<string>("");
  // The most recent timestamp (in seconds) successfully applied to
  // the candle series. lightweight-charts' ``update()`` rejects calls
  // with a time strictly older than the series' last bar — when the
  // user re-opens a coin they previously viewed, the WS store still
  // holds a stale ``lastCandles`` entry whose time can predate the
  // freshly-seeded historical bar. We track the last applied time
  // ourselves and silently drop stale bars instead of letting the
  // chart throw "Cannot update oldest data".
  const lastAppliedTimeRef = useRef<number>(-1);

  // Subscribe to the live candle for this exact (coin, interval).
  // Zustand's selector compares by reference so we only re-render
  // when *this* key's bar changes — unrelated chart updates flowing
  // through other tabs are filtered at the store layer.
  const liveCandle = useWsStore((s) => s.lastCandles[candleKey(coin, interval)]);
  const activeKey = candleKey(coin, interval);

  // Indicator toggles. Read directly from the indicator store inside
  // the chart so the parent (CoinView) doesn't have to subscribe to
  // either the indicator store or the live candle store — keeping the
  // per-WS-push re-render scope confined to this component instead of
  // bubbling through every panel in CoinView.
  const showSMA7 = useIndicator("sma7");
  const showSMA20 = useIndicator("sma20", true);
  const showEMA50 = useIndicator("ema50");
  const showVWAP = useIndicator("vwap");

  // Historical bars with the latest WS bar merged in. Used as the
  // input to the indicator math so SMA/EMA/VWAP move in lockstep with
  // the live candle bar instead of staying one bar behind until the
  // next REST refetch. Skipped during the keepPreviousData window of a
  // coin transition — patching an ETH live bar onto a BTC candles
  // array would corrupt the indicator output.
  const livePatchedCandles = useMemo(() => {
    if (isPlaceholderData) return candles;
    if (!liveCandle || candles.length === 0) return candles;
    const last = candles.at(-1);
    if (last === undefined) return candles;
    if (last.timestamp_ms === liveCandle.timestamp_ms) {
      return [...candles.slice(0, -1), liveCandle];
    }
    if (liveCandle.timestamp_ms > last.timestamp_ms) {
      return [...candles, liveCandle];
    }
    return candles;
  }, [candles, liveCandle, isPlaceholderData]);

  const overlays = useMemo<OverlayLine[]>(() => {
    const lines: OverlayLine[] = [];
    if (showSMA7)
      lines.push({ key: "sma7", data: computeSMA(livePatchedCandles, 7), color: SMA_7_COLOR });
    if (showSMA20)
      lines.push({ key: "sma20", data: computeSMA(livePatchedCandles, 20), color: SMA_20_COLOR });
    if (showEMA50)
      lines.push({ key: "ema50", data: computeEMA(livePatchedCandles, 50), color: EMA_50_COLOR });
    if (showVWAP)
      lines.push({ key: "vwap", data: computeVWAP(livePatchedCandles), color: VWAP_COLOR });
    return lines;
  }, [livePatchedCandles, showSMA7, showSMA20, showEMA50, showVWAP]);

  // ── Chart creation ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: chartDarkColors.bg },
        textColor: chartDarkColors.text,
        fontSize: 11,
        panes: {
          separatorColor: chartDarkColors.paneSeparator,
          separatorHoverColor: chartDarkColors.paneSeparatorHover,
          enableResize: true,
        },
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: chartDarkColors.panelBorder },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: chartDarkColors.crosshairLine,
          width: 1,
          style: 3,
          labelBackgroundColor: chartDarkColors.crosshairLabelBg,
        },
        horzLine: {
          color: chartDarkColors.crosshairLine,
          width: 1,
          style: 3,
          labelBackgroundColor: chartDarkColors.crosshairLabelBg,
        },
      },
      rightPriceScale: {
        borderColor: chartDarkColors.panelBorder,
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
      timeScale: {
        borderColor: chartDarkColors.panelBorder,
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height,
    });
    chartRef.current = chart;

    // Pane 0 (candles) — exists by default. Set its stretch factor.
    chart.panes()[PANE_INDEX_CANDLES].setStretchFactor(STRETCH_CANDLES);

    // Pane 1 (volume) — explicit second pane.
    const volumePane = chart.addPane();
    volumePane.setStretchFactor(STRETCH_VOLUME);
    volumePaneRef.current = volumePane;

    const candleSeries = chart.addSeries(
      CandlestickSeries,
      {
        upColor: chartDarkColors.up,
        downColor: chartDarkColors.down,
        borderVisible: false,
        wickUpColor: chartDarkColors.up,
        wickDownColor: chartDarkColors.down,
      },
      PANE_INDEX_CANDLES,
    );
    candleSeriesRef.current = candleSeries;

    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        color: colors.grey,
        priceFormat: { type: "volume" },
        priceScaleId: "right",
        priceLineVisible: false,
        lastValueVisible: true,
      },
      PANE_INDEX_VOLUME,
    );
    volumeSeriesRef.current = volumeSeries;

    // Volume pane's right price scale needs to be configured explicitly —
    // the chart-level rightPriceScale options only apply to pane 0.
    chart.priceScale("right", PANE_INDEX_VOLUME).applyOptions({
      visible: true,
      borderColor: chartDarkColors.panelBorder,
      scaleMargins: { top: 0.1, bottom: 0.05 },
    });

    // Top-left legend in the volume pane (TradingView-style "VOL 1.23M").
    // Driven by the crosshair-move subscription below.
    volumeLegendRef.current = createTextWatermark(volumePane, {
      visible: true,
      horzAlign: "left",
      vertAlign: "top",
      lines: legendLines("VOL", "—"),
    });

    // Crosshair → legend. One subscription updates whichever legends exist.
    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const volLegend = volumeLegendRef.current;
      if (volLegend) {
        const v = valueFromCrosshair(param, volumeSeriesRef.current);
        volLegend.applyOptions({
          lines: legendLines("VOL", v == null ? "—" : formatUSD(v)),
        });
      }
      const oiLegend = oiLegendRef.current;
      if (oiLegend) {
        const v = valueFromCrosshair(param, oiSeriesRef.current);
        oiLegend.applyOptions({
          lines: legendLines("OI", v == null ? "—" : formatUSD(v)),
        });
      }
      const fundingLegend = fundingLegendRef.current;
      if (fundingLegend) {
        const v = valueFromCrosshair(param, fundingSeriesRef.current);
        fundingLegend.applyOptions({
          lines: legendLines("FUND", v == null ? "—" : formatFundingRate(v)),
        });
      }
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    // Mouseup catches the end of any pane separator drag — the buttons
    // snap to their new position on release. Deliberately not wired
    // into the crosshair handler: that would re-measure every pane on
    // every mouse move across the chart, which is extra work on the
    // hottest interaction path for no visible benefit (buttons only
    // need to update at drag end, not during the drag).
    const handleMouseUp = () => recomputePaneLayoutRef.current();
    containerRef.current.addEventListener("mouseup", handleMouseUp);

    let rafId = 0;
    const resizeObserver = new ResizeObserver((entries) => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (entries[0]) {
          chart.applyOptions({ width: entries[0].contentRect.width });
          recomputePaneLayoutRef.current();
        }
      });
    });
    resizeObserver.observe(containerRef.current);

    // Initial layout pass — fires after the chart and volume pane
    // exist so the buttons appear without waiting for a resize event.
    recomputePaneLayoutRef.current();

    return () => {
      cancelAnimationFrame(rafId);
      if (recomputeRafRef.current) {
        cancelAnimationFrame(recomputeRafRef.current);
        recomputeRafRef.current = 0;
      }
      resizeObserver.disconnect();
      containerRef.current?.removeEventListener("mouseup", handleMouseUp);
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      overlaySeriesRefs.current.clear();
      oiSeriesRef.current = null;
      oiPaneRef.current = null;
      fundingSeriesRef.current = null;
      fundingPaneRef.current = null;
      volumeLegendRef.current = null;
      oiLegendRef.current = null;
      fundingLegendRef.current = null;
      volumePaneRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
    // Chart is created once for the lifetime of the component.
    // ``height`` changes are handled below via ``applyOptions`` —
    // including it as a dep would tear down and recreate the whole
    // chart (series, panes, legends, crosshair subs) on every pixel
    // the parent resizes us by.
  }, []);

  // Apply ``height`` prop changes without rebuilding the chart.
  useEffect(() => {
    chartRef.current?.applyOptions({ height });
  }, [height]);

  // ── Pan-to-load older bars ──────────────────────────────────
  // Subscribe once (per chart lifecycle) to the time-scale's visible
  // logical range. Whenever the left edge of the view enters the
  // trigger zone, ask the parent for another page. Refs are used so
  // the handler picks up the latest prop values without resubscribing
  // (which would leak LWC subscriptions across renders).
  const onLoadOlderRef = useRef(onLoadOlder);
  onLoadOlderRef.current = onLoadOlder;
  const hasMoreOlderRef = useRef(hasMoreOlder);
  hasMoreOlderRef.current = hasMoreOlder;
  const isLoadingOlderRef = useRef(isLoadingOlder);
  isLoadingOlderRef.current = isLoadingOlder;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const handler = (range: { from: number; to: number } | null): void => {
      if (!range) return;
      if (!hasMoreOlderRef.current || isLoadingOlderRef.current) return;
      // ``from`` can go slightly negative when the user has scrolled
      // past the first bar; trigger based on absolute bars from the
      // series start rather than the raw value to keep the condition
      // readable.
      if (range.from <= LOAD_OLDER_TRIGGER_BARS) {
        onLoadOlderRef.current?.();
      }
    };
    const timeScale = chart.timeScale();
    timeScale.subscribeVisibleLogicalRangeChange(handler);
    return () => {
      timeScale.unsubscribeVisibleLogicalRangeChange(handler);
    };
  }, []);

  // ── Candle + volume data ────────────────────────────────────
  const candleData = useMemo<CandlestickData[]>(
    () =>
      candles.map((c) => ({
        time: msToSec(c.timestamp_ms) as CandlestickData["time"],
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    [candles],
  );

  // c.volume is in coin units; multiply by c.close to get USD-denominated
  // bar volume so the histogram, legend, and right-axis labels all show
  // dollar values consistent with the rest of the dashboard.
  const volumeData = useMemo<HistogramData[]>(
    () =>
      candles.map((c) => ({
        time: msToSec(c.timestamp_ms) as HistogramData["time"],
        value: c.volume * c.close,
        color: c.close >= c.open ? chartDarkColors.volumeUp : chartDarkColors.volumeDown,
      })),
    [candles],
  );

  // Apply a single live bar to the candle + volume series + legend.
  // Defined inside the component (not memoized) because it closes
  // over refs only and is called from two effects below — keeping
  // it inline avoids both a useCallback dep dance and the tempting
  // bug of duplicating the update logic.
  function applyLiveBar(bar: CandleItem): void {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !volumeSeries) return;
    const timeSec = msToSec(bar.timestamp_ms);
    // Drop stale bars: lightweight-charts rejects update() with a
    // time strictly older than the series' last bar. This happens
    // when the WS store still holds a previous-session bar for a
    // coin the user just re-opened. Equal times are allowed — that's
    // the in-place patch path for the still-open bar.
    if (timeSec < lastAppliedTimeRef.current) return;
    const time = timeSec as Time;
    candleSeries.update({
      time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    });
    volumeSeries.update({
      time,
      value: bar.volume * bar.close,
      color: bar.close >= bar.open ? "#26a69a60" : "#ef535060",
    });
    lastAppliedTimeRef.current = timeSec;
    const legend = volumeLegendRef.current;
    if (legend) {
      legend.applyOptions({
        lines: legendLines("VOL", formatUSD(bar.volume * bar.close)),
      });
    }
  }

  // Tracks how many bars the series held before the most recent
  // ``setData`` call. Used to detect pan-to-load extensions (same
  // key, grew by N) vs coin changes (different key) so the view can
  // preserve the user's scroll position on extensions instead of
  // ``fitContent``-ing them back to the right edge.
  const prevCandleCountRef = useRef<number>(0);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    const chart = chartRef.current;
    const timeScale = chart?.timeScale();
    const wasSeededFor = seededKeyRef.current;
    const isCoinChange = wasSeededFor !== activeKey;
    const prevLength = prevCandleCountRef.current;
    const newLength = candleData.length;
    // Capture the view before replacing data — only meaningful on
    // an extension, where we need to shift indices forward by the
    // new-older count to keep the same bars visible.
    const savedRange =
      !isCoinChange && newLength > prevLength
        ? timeScale?.getVisibleLogicalRange()
        : null;

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);

    if (isCoinChange) {
      timeScale?.fitContent();
    } else if (savedRange) {
      // Older bars prepended — LWC shifts indices, so bar that was
      // at logical index K is now at K + (newLength - prevLength).
      // Offset the visible range by that delta so the user's scroll
      // position looks the same post-load.
      const delta = newLength - prevLength;
      timeScale?.setVisibleLogicalRange({
        from: savedRange.from + delta,
        to: savedRange.to + delta,
      });
    }

    // Record which key the candle series now holds. The closure
    // captures `activeKey` at the moment this effect runs, which
    // is exactly when fresh REST data arrived for the active coin.
    //
    // CRITICAL: this effect intentionally does NOT depend on
    // `activeKey`. With React Query's `keepPreviousData`, the
    // `candles` array reference is unchanged during a coin
    // transition (it's a placeholder of the previous coin's bars).
    // If we re-ran this effect on every `activeKey` change, we'd
    // overwrite seededKeyRef to the new coin while the series
    // still held the previous coin's data, and the live-update
    // path would then patch the new coin's WS bars onto the wrong
    // historical series. Letting candleData drive the effect
    // guarantees we only re-seed when real data arrives for the
    // current coin.
    seededKeyRef.current = activeKey;
    prevCandleCountRef.current = newLength;
    // Reset the stale-bar guard to the last historical bar's time
    // so any older entry still cached in the WS store is rejected
    // by applyLiveBar instead of being passed to lightweight-charts'
    // update(), which would throw "Cannot update oldest data".
    const lastCandle = candleData.at(-1);
    lastAppliedTimeRef.current =
      lastCandle !== undefined ? (lastCandle.time as number) : -1;

    // Initial / data-update legend population: when not hovering, show the
    // most recent volume bar so the watermark isn't stuck on "—".
    const legend = volumeLegendRef.current;
    const lastBar = volumeData.at(-1);
    if (legend && lastBar) {
      legend.applyOptions({
        lines: legendLines("VOL", formatUSD(lastBar.value)),
      });
    }

    // Replay any live bar that arrived before the historical seed.
    // Without this, the very first WS push for a freshly-mounted
    // chart would be silently dropped and the chart would stay on
    // the REST snapshot until the next push. applyLiveBar's stale
    // guard handles the case where the cached bar predates the seed.
    const pending = useWsStore.getState().lastCandles[activeKey];
    if (pending) {
      applyLiveBar(pending);
    }
  }, [candleData, volumeData]);

  // Live WS bar → incremental update on the candle + volume series.
  // lightweight-charts' update() is bar-aware: same `time` patches
  // the latest bar in place, advanced `time` appends a new bar.
  // The seededKeyRef gate prevents applying ETH bars to a chart
  // that still holds BTC data during a coin transition (when
  // keepPreviousData is in effect upstream).
  useEffect(() => {
    if (seededKeyRef.current !== activeKey) return;
    if (!liveCandle) return;
    applyLiveBar(liveCandle);
  }, [liveCandle, activeKey]);

  // ── Overlay lines (SMA / EMA / VWAP) on the candle pane ────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const incoming = new Set(overlays.map((o) => o.key));
    const existing = overlaySeriesRefs.current;

    // Remove series no longer requested
    for (const [key, series] of existing) {
      if (!incoming.has(key)) {
        chart.removeSeries(series);
        existing.delete(key);
      }
    }

    // Add or update
    for (const overlay of overlays) {
      let series = existing.get(overlay.key);
      if (!series) {
        series = chart.addSeries(
          LineSeries,
          {
            color: overlay.color,
            lineWidth: (overlay.lineWidth ?? 1.5) as 1 | 2 | 3 | 4,
            lineStyle: overlay.lineStyle ?? LineStyle.Solid,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
          },
          PANE_INDEX_CANDLES,
        );
        existing.set(overlay.key, series);
      }
      // IndicatorPoint and LineData<Time> have identical runtime
      // shape — `Time` is just a branded number alias and `value` is
      // already `number`. Cast through `unknown` to skip the per-push
      // map allocation that would otherwise produce ~720 fresh
      // objects per overlay on every WS bar.
      series.setData(overlay.data as unknown as LineData<Time>[]);
    }
  }, [overlays]);

  // OI snapshots arrive at sub-candle intervals. Because all panes share one
  // time axis in LWC, extra OI timestamps expand the x-grid and make candle
  // bars appear far too narrow. Re-sample OI onto the exact candle timestamps:
  // for each candle bar, take the last OI value at or before that bar's time.
  const oiAligned = useMemo(() => {
    if (!oiData || oiData.length === 0 || candles.length === 0) return [];
    const sorted = [...oiData].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
    const result: { time: Time; value: number }[] = [];
    let j = 0;
    for (const candle of candles) {
      while (j + 1 < sorted.length && sorted[j + 1].timestamp_ms <= candle.timestamp_ms) j++;
      if (sorted[j].timestamp_ms <= candle.timestamp_ms) {
        result.push({ time: msToSec(candle.timestamp_ms) as Time, value: sorted[j].open_interest_usd });
      }
    }
    return result;
  }, [oiData, candles]);

  // Funding snapshots also arrive at sub-candle intervals — same alignment
  // story as OI. Re-sample funding onto each candle's timestamp using the
  // last value at or before the bar so the histogram lines up cleanly with
  // candles instead of expanding the x-grid into a dot-plot.
  const fundingAligned = useMemo(() => {
    if (!fundingData || fundingData.length === 0 || candles.length === 0) return [];
    const sorted = [...fundingData].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
    const result: { time: Time; value: number; color: string }[] = [];
    let j = 0;
    for (const candle of candles) {
      while (j + 1 < sorted.length && sorted[j + 1].timestamp_ms <= candle.timestamp_ms) j++;
      if (sorted[j].timestamp_ms <= candle.timestamp_ms) {
        const rate = sorted[j].funding_rate;
        result.push({
          time: msToSec(candle.timestamp_ms) as Time,
          value: rate,
          color: rate >= 0 ? colors.teal : colors.red,
        });
      }
    }
    return result;
  }, [fundingData, candles]);

  // ── OI sub-pane ─────────────────────────────────────────────
  // v5 panes API: addPane()/removePane() instead of priceScaleId margin hacks.
  // Toggling OI on/off cleanly creates or removes a real pane; the other
  // panes reflow according to their stretch factors. The pane is held by
  // IPaneApi reference (not numeric index) so its position stays correct
  // even if the funding pane is added/removed alongside it.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const enabled = showOI && oiAligned.length > 0;

    if (enabled) {
      if (!oiSeriesRef.current) {
        const oiPane = chart.addPane();
        oiPane.setStretchFactor(STRETCH_SUB_PANE);
        oiPaneRef.current = oiPane;

        oiSeriesRef.current = chart.addSeries(
          AreaSeries,
          {
            topColor: chartDarkColors.areaTintTeal,
            bottomColor: "transparent",
            lineColor: colors.teal,
            lineWidth: 1,
            priceScaleId: "right",
            priceFormat: { type: "volume" },
            lastValueVisible: true,
            priceLineVisible: false,
          },
          oiPane.paneIndex(),
        );

        // Same explicit price scale config as the volume pane.
        chart.priceScale("right", oiPane.paneIndex()).applyOptions({
          visible: true,
          borderColor: chartDarkColors.panelBorder,
          scaleMargins: { top: 0.1, bottom: 0.05 },
        });

        // Matching legend in the OI pane.
        oiLegendRef.current = createTextWatermark(oiPane, {
          visible: true,
          horzAlign: "left",
          vertAlign: "top",
          lines: legendLines("OI", "—"),
        });
      }
      oiSeriesRef.current.setData(oiAligned);

      // Populate the legend with the latest OI value (mirrors the volume legend).
      const lastOi = oiData?.at(-1);
      if (oiLegendRef.current && lastOi) {
        oiLegendRef.current.applyOptions({
          lines: legendLines("OI", formatUSD(lastOi.open_interest_usd)),
        });
      }
      recomputePaneLayout();
    } else if (oiSeriesRef.current && oiPaneRef.current) {
      // v5: removePane also removes all series within it. Calling removeSeries
      // first would auto-remove the now-empty pane, making the subsequent
      // removePane call fail with "Invalid pane index". Resolve the current
      // index from the pane ref so a removed funding pane above us doesn't
      // leave a stale numeric index behind.
      chart.removePane(oiPaneRef.current.paneIndex());
      oiSeriesRef.current = null;
      oiPaneRef.current = null;
      oiLegendRef.current = null;
      recomputePaneLayout();
    }
  }, [showOI, oiAligned, oiData, recomputePaneLayout]); // oiData kept so legend "last value" stays fresh

  // ── Funding sub-pane ────────────────────────────────────────
  // Histogram coloured by sign — matches the standalone FundingChart
  // panel. Replaces the previous series-marker rendering, which produced
  // a dot-plot above/below every candle when funding snapshots were
  // dense. Pane-ref tracking mirrors OI for the same reordering reason.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const enabled = showFunding && fundingAligned.length > 0;

    if (enabled) {
      if (!fundingSeriesRef.current) {
        const fundingPane = chart.addPane();
        fundingPane.setStretchFactor(STRETCH_SUB_PANE);
        fundingPaneRef.current = fundingPane;

        fundingSeriesRef.current = chart.addSeries(
          HistogramSeries,
          {
            priceFormat: fundingPriceFormat,
            priceScaleId: "right",
            base: 0,
            priceLineVisible: false,
            lastValueVisible: true,
          },
          fundingPane.paneIndex(),
        );

        chart.priceScale("right", fundingPane.paneIndex()).applyOptions({
          visible: true,
          borderColor: chartDarkColors.panelBorder,
          scaleMargins: { top: 0.1, bottom: 0.1 },
        });

        fundingLegendRef.current = createTextWatermark(fundingPane, {
          visible: true,
          horzAlign: "left",
          vertAlign: "top",
          lines: legendLines("FUND", "—"),
        });
      }
      fundingSeriesRef.current.setData(fundingAligned);

      const lastFunding = fundingData?.at(-1);
      if (fundingLegendRef.current && lastFunding) {
        fundingLegendRef.current.applyOptions({
          lines: legendLines("FUND", formatFundingRate(lastFunding.funding_rate)),
        });
      }
      recomputePaneLayout();
    } else if (fundingSeriesRef.current && fundingPaneRef.current) {
      chart.removePane(fundingPaneRef.current.paneIndex());
      fundingSeriesRef.current = null;
      fundingPaneRef.current = null;
      fundingLegendRef.current = null;
      recomputePaneLayout();
    }
  }, [showFunding, fundingAligned, fundingData, recomputePaneLayout]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%", height }}>
      {paneLayout.map((entry, i) => {
        const canMoveUp = i > 0;
        const canMoveDown = i < paneLayout.length - 1;
        return (
          <div
            key={entry.key}
            // Inset from the right edge to clear the price scale labels.
            // Wrapper has pointer-events: none so chart drag/scroll still
            // works through the gaps; only the buttons themselves grab clicks.
            style={{
              position: "absolute",
              top: entry.top + 4,
              right: 88,
              zIndex: 5,
              pointerEvents: "none",
            }}
            className="flex gap-0.5"
          >
            <button
              type="button"
              disabled={!canMoveUp}
              onClick={() => movePane(entry.paneIndex, entry.paneIndex - 1)}
              title={`Move ${entry.label} pane up`}
              aria-label={`Move ${entry.label} pane up`}
              style={{ pointerEvents: "auto" }}
              className="w-4 h-4 flex items-center justify-center text-[10px] font-mono leading-none text-gray-500 hover:text-gray-200 hover:bg-gray-800/80 rounded disabled:opacity-25 disabled:hover:bg-transparent disabled:hover:text-gray-500 transition-colors"
            >
              ↑
            </button>
            <button
              type="button"
              disabled={!canMoveDown}
              onClick={() => movePane(entry.paneIndex, entry.paneIndex + 1)}
              title={`Move ${entry.label} pane down`}
              aria-label={`Move ${entry.label} pane down`}
              style={{ pointerEvents: "auto" }}
              className="w-4 h-4 flex items-center justify-center text-[10px] font-mono leading-none text-gray-500 hover:text-gray-200 hover:bg-gray-800/80 rounded disabled:opacity-25 disabled:hover:bg-transparent disabled:hover:text-gray-500 transition-colors"
            >
              ↓
            </button>
          </div>
        );
      })}
    </div>
  );
});
