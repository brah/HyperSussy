import { memo, useEffect, useMemo, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type SeriesMarker,
  type Time,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { CandleItem, OISnapshotItem, FundingSnapshotItem } from "../../api/types";
import type { IndicatorPoint } from "../../utils/indicators";
import { colors } from "../../theme/colors";
import { msToSec } from "../../utils/time";
import { formatFundingRate } from "../../utils/format";

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

  // ── Chart creation ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#000000" },
        textColor: "#9ca3af",
        fontSize: 11,
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
      rightPriceScale: { borderColor: "#1a1a1a", scaleMargins: { top: 0.05, bottom: 0.25 } },
      timeScale: { borderColor: "#1a1a1a", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    candleSeriesRef.current = candleSeries;

    const volumeSeries = chart.addHistogramSeries({
      color: colors.grey,
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

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
      overlaySeriesRefs.current.clear();
      oiSeriesRef.current = null;
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

  const volumeData = useMemo<HistogramData[]>(
    () =>
      candles.map((c) => ({
        time: msToSec(c.timestamp_ms) as HistogramData["time"],
        value: c.volume,
        color: c.close >= c.open ? "#26a69a60" : "#ef535060",
      })),
    [candles],
  );

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();
  }, [candleData, volumeData]);

  // ── Overlay lines (SMA / EMA / VWAP) ───────────────────────
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
        series = chart.addLineSeries({
          color: overlay.color,
          lineWidth: (overlay.lineWidth ?? 1.5) as 1 | 2 | 3 | 4,
          lineStyle: overlay.lineStyle ?? LineStyle.Solid,
          crosshairMarkerVisible: false,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        existing.set(overlay.key, series);
      }
      series.setData(
        overlay.data.map((p) => ({ time: p.time as Time, value: p.value })),
      );
    }
  }, [overlays]);

  // ── OI sub-pane ─────────────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (showOI && oiData && oiData.length > 0) {
      // Adjust volume pane to make room
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.9, bottom: 0 },
      });

      let series = oiSeriesRef.current;
      if (!series) {
        series = chart.addAreaSeries({
          topColor: `${colors.teal}30`,
          bottomColor: "transparent",
          lineColor: colors.teal,
          lineWidth: 1,
          priceScaleId: "oi",
          lastValueVisible: true,
          priceLineVisible: false,
        });
        chart.priceScale("oi").applyOptions({
          scaleMargins: { top: 0.7, bottom: 0.2 },
        });
        oiSeriesRef.current = series;
      }
      series.setData(
        oiData.map((d) => ({
          time: msToSec(d.timestamp_ms) as Time,
          value: d.open_interest_usd,
        })),
      );
    } else {
      // Remove OI series and restore volume pane
      if (oiSeriesRef.current && chart) {
        chart.removeSeries(oiSeriesRef.current);
        oiSeriesRef.current = null;
      }
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
    }
  }, [showOI, oiData]);

  // ── Funding rate markers ────────────────────────────────────
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    if (!showFundingMarkers || !fundingData || fundingData.length === 0) {
      candleSeries.setMarkers([]);
      return;
    }

    // Only show markers within candle time range
    const minTime = candles.length > 0 ? msToSec(candles[0].timestamp_ms) : 0;
    const maxTime =
      candles.length > 0 ? msToSec(candles[candles.length - 1].timestamp_ms) : Infinity;

    const markers: SeriesMarker<Time>[] = fundingData
      .filter((f) => {
        const t = msToSec(f.timestamp_ms);
        return t >= minTime && t <= maxTime && Math.abs(f.funding_rate) > 0.00005;
      })
      .map((f) => ({
        time: msToSec(f.timestamp_ms) as Time,
        position: f.funding_rate >= 0 ? ("aboveBar" as const) : ("belowBar" as const),
        color: f.funding_rate >= 0 ? colors.teal : colors.red,
        shape: "circle" as const,
        text: formatFundingRate(f.funding_rate),
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));

    candleSeries.setMarkers(markers);
  }, [showFundingMarkers, fundingData, candles]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
});
