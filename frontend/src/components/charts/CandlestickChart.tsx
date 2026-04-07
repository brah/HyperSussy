import { memo, useEffect, useMemo, useRef } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  createTextWatermark,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type ITextWatermarkPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { CandleItem, OISnapshotItem, FundingSnapshotItem } from "../../api/types";
import type { IndicatorPoint } from "../../utils/indicators";
import { colors } from "../../theme/colors";
import { msToSec } from "../../utils/time";
import { formatFundingRate, formatUSD } from "../../utils/format";

export interface OverlayLine {
  key: string;
  data: IndicatorPoint[];
  color: string;
  lineWidth?: number;
  lineStyle?: LineStyle;
}

interface CandlestickChartProps {
  candles: CandleItem[];
  height?: number;
  overlays?: OverlayLine[];
  oiData?: OISnapshotItem[];
  showOI?: boolean;
  fundingData?: FundingSnapshotItem[];
  showFundingMarkers?: boolean;
}

// Pane layout: relative stretch factors (flex-grow style).
//   pane 0: candles            ── default pane created with the chart
//   pane 1: volume             ── always present
//   pane 2: OI (open interest) ── only when showOI=true
const PANE_INDEX_CANDLES = 0;
const PANE_INDEX_VOLUME = 1;
const STRETCH_CANDLES = 5;
const STRETCH_VOLUME = 1;
const STRETCH_OI = 1.5;

const LEGEND_FONT_SIZE = 11;
const LEGEND_FONT_FAMILY = "ui-monospace, SFMono-Regular, monospace";
const LEGEND_COLOR = "#9ca3af";

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
  candles,
  height = 400,
  overlays = [],
  oiData,
  showOI = false,
  fundingData,
  showFundingMarkers = false,
}: Readonly<CandlestickChartProps>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlaySeriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const oiSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const oiPaneIndexRef = useRef<number | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const volumeLegendRef = useRef<ITextWatermarkPluginApi<Time> | null>(null);
  const oiLegendRef = useRef<ITextWatermarkPluginApi<Time> | null>(null);

  // ── Chart creation ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#000000" },
        textColor: "#9ca3af",
        fontSize: 11,
        panes: {
          separatorColor: "#1a1a1a",
          separatorHoverColor: "#2a2a2a",
          enableResize: true,
        },
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#1a1a1a" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#374151", width: 1, style: 3, labelBackgroundColor: "#1f2937" },
        horzLine: { color: "#374151", width: 1, style: 3, labelBackgroundColor: "#1f2937" },
      },
      rightPriceScale: {
        borderColor: "#1a1a1a",
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
      timeScale: { borderColor: "#1a1a1a", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height,
    });
    chartRef.current = chart;

    // Pane 0 (candles) — exists by default. Set its stretch factor.
    chart.panes()[PANE_INDEX_CANDLES].setStretchFactor(STRETCH_CANDLES);

    // Pane 1 (volume) — explicit second pane.
    const volumePane = chart.addPane();
    volumePane.setStretchFactor(STRETCH_VOLUME);

    const candleSeries = chart.addSeries(
      CandlestickSeries,
      {
        upColor: "#26a69a",
        downColor: "#ef5350",
        borderVisible: false,
        wickUpColor: "#26a69a",
        wickDownColor: "#ef5350",
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
      borderColor: "#1a1a1a",
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
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    let rafId = 0;
    const resizeObserver = new ResizeObserver((entries) => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (entries[0]) {
          chart.applyOptions({ width: entries[0].contentRect.width });
        }
      });
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      overlaySeriesRefs.current.clear();
      oiSeriesRef.current = null;
      oiPaneIndexRef.current = null;
      markersPluginRef.current = null;
      volumeLegendRef.current = null;
      oiLegendRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height]);

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
        color: c.close >= c.open ? "#26a69a60" : "#ef535060",
      })),
    [candles],
  );

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();

    // Initial / data-update legend population: when not hovering, show the
    // most recent volume bar so the watermark isn't stuck on "—".
    const legend = volumeLegendRef.current;
    const lastBar = volumeData.at(-1);
    if (legend && lastBar) {
      legend.applyOptions({
        lines: legendLines("VOL", formatUSD(lastBar.value)),
      });
    }
  }, [candleData, volumeData]);

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
      series.setData(
        overlay.data.map((p) => ({ time: p.time as Time, value: p.value })),
      );
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

  // ── OI sub-pane ─────────────────────────────────────────────
  // v5 panes API: addPane()/removePane() instead of priceScaleId margin hacks.
  // Toggling OI on/off cleanly creates or removes a real pane; the other
  // panes reflow according to their stretch factors.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const enabled = showOI && oiAligned.length > 0;

    if (enabled) {
      if (!oiSeriesRef.current) {
        const oiPane = chart.addPane();
        oiPane.setStretchFactor(STRETCH_OI);
        oiPaneIndexRef.current = oiPane.paneIndex();

        oiSeriesRef.current = chart.addSeries(
          AreaSeries,
          {
            topColor: `${colors.teal}30`,
            bottomColor: "transparent",
            lineColor: colors.teal,
            lineWidth: 1,
            priceScaleId: "right",
            priceFormat: { type: "volume" },
            lastValueVisible: true,
            priceLineVisible: false,
          },
          oiPaneIndexRef.current,
        );

        // Same explicit price scale config as the volume pane.
        chart.priceScale("right", oiPaneIndexRef.current).applyOptions({
          visible: true,
          borderColor: "#1a1a1a",
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
    } else if (oiSeriesRef.current && oiPaneIndexRef.current != null) {
      // v5: removePane also removes all series within it. Calling removeSeries
      // first would auto-remove the now-empty pane, making the subsequent
      // removePane call fail with "Invalid pane index".
      chart.removePane(oiPaneIndexRef.current);
      oiSeriesRef.current = null;
      oiPaneIndexRef.current = null;
      oiLegendRef.current = null;
    }
  }, [showOI, oiAligned, oiData]); // oiData kept so legend "last value" stays fresh

  // ── Funding rate markers ────────────────────────────────────
  // v5 moved markers to a separate plugin: createSeriesMarkers(series, markers)
  // returns an ISeriesMarkersPluginApi whose own setMarkers() is the update path.
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    if (!showFundingMarkers || !fundingData || fundingData.length === 0) {
      markersPluginRef.current?.setMarkers([]);
      return;
    }

    const minTime = candles.length > 0 ? msToSec(candles[0].timestamp_ms) : 0;
    const maxTime =
      candles.length > 0
        ? msToSec(candles[candles.length - 1].timestamp_ms)
        : Infinity;

    const markers: SeriesMarker<Time>[] = fundingData
      .filter((f) => {
        const t = msToSec(f.timestamp_ms);
        return t >= minTime && t <= maxTime && Math.abs(f.funding_rate) > 0.00005;
      })
      .sort((a, b) => a.timestamp_ms - b.timestamp_ms)
      .map((f) => ({
        time: msToSec(f.timestamp_ms) as Time,
        position: f.funding_rate >= 0 ? ("aboveBar" as const) : ("belowBar" as const),
        color: f.funding_rate >= 0 ? colors.teal : colors.red,
        shape: "circle" as const,
        text: formatFundingRate(f.funding_rate),
      }));

    if (!markersPluginRef.current) {
      markersPluginRef.current = createSeriesMarkers(candleSeries, markers);
    } else {
      markersPluginRef.current.setMarkers(markers);
    }
  }, [showFundingMarkers, fundingData, candles]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
