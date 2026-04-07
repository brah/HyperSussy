/**
 * Pure indicator computation functions for candlestick chart overlays.
 *
 * Each function accepts CandleItem[] and returns an array of
 * { time, value } points ready for lightweight-charts LineSeries.setData().
 */

import type { CandleItem } from "../api/types";
import { msToSec } from "./time";

export interface IndicatorPoint {
  time: number; // UTCTimestamp (seconds)
  value: number;
}

// Line colors for each indicator
export const SMA_7_COLOR = "#2196F3";
export const SMA_20_COLOR = "#FF9800";
export const EMA_50_COLOR = "#9C27B0";
export const VWAP_COLOR = "#c65102"; // colors.orange

/** Simple Moving Average over `period` close prices. */
export function computeSMA(candles: CandleItem[], period: number): IndicatorPoint[] {
  if (candles.length < period) return [];
  const result: IndicatorPoint[] = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close;
    if (i >= period) sum -= candles[i - period].close;
    if (i >= period - 1) {
      result.push({
        time: msToSec(candles[i].timestamp_ms),
        value: sum / period,
      });
    }
  }
  return result;
}

/** Exponential Moving Average over `period` close prices. */
export function computeEMA(candles: CandleItem[], period: number): IndicatorPoint[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const result: IndicatorPoint[] = [];

  // Seed with SMA of first `period` candles
  let sum = 0;
  for (let i = 0; i < period; i++) sum += candles[i].close;
  let ema = sum / period;
  result.push({ time: msToSec(candles[period - 1].timestamp_ms), value: ema });

  for (let i = period; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
    result.push({ time: msToSec(candles[i].timestamp_ms), value: ema });
  }
  return result;
}

/** Volume-Weighted Average Price, resetting at UTC midnight boundaries. */
export function computeVWAP(candles: CandleItem[]): IndicatorPoint[] {
  if (candles.length === 0) return [];
  const result: IndicatorPoint[] = [];
  let cumVolume = 0;
  let cumTPV = 0; // cumulative (typical_price * volume)
  let prevDay = -1;

  for (const c of candles) {
    const day = Math.floor(c.timestamp_ms / 86_400_000);
    if (day !== prevDay) {
      // Reset at new UTC day
      cumVolume = 0;
      cumTPV = 0;
      prevDay = day;
    }
    const tp = (c.high + c.low + c.close) / 3;
    cumTPV += tp * c.volume;
    cumVolume += c.volume;
    if (cumVolume > 0) {
      result.push({
        time: msToSec(c.timestamp_ms),
        value: cumTPV / cumVolume,
      });
    }
  }
  return result;
}
