import { useEffect, useMemo, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { CandleItem } from "../../api/types";
import { colors } from "../../theme/colors";
import { msToSec } from "../../utils/time";

interface CandlestickChartProps {
  candles: CandleItem[];
  height?: number;
}

export function CandlestickChart({
  candles,
  height = 400,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: colors.bg },
        textColor: colors.grey,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: colors.grid },
      timeScale: { borderColor: colors.grid, timeVisible: true },
      width: containerRef.current.clientWidth,
      height,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: colors.teal,
      downColor: colors.red,
      borderVisible: false,
      wickUpColor: colors.teal,
      wickDownColor: colors.red,
    });
    candleSeriesRef.current = candleSeries;

    const volumeSeries = chart.addHistogramSeries({
      color: colors.grey,
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
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
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height]);

  const candleData = useMemo<CandlestickData[]>(
    () =>
      candles.map((c) => ({
        time: msToSec(c.timestamp_ms) as CandlestickData["time"],
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    [candles]
  );

  const volumeData = useMemo<HistogramData[]>(
    () =>
      candles.map((c) => ({
        time: msToSec(c.timestamp_ms) as HistogramData["time"],
        value: c.volume,
        color: c.close >= c.open ? `${colors.teal}80` : `${colors.red}80`,
      })),
    [candles]
  );

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();
  }, [candleData, volumeData]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
