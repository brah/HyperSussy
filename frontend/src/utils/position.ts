/**
 * Position-derived helpers shared across wallet and market tables.
 */

import type { CoinPositionItem, PositionItem } from "../api/types";

type PositionWithLiq = {
  liquidation_price: number | null;
  mark_price: number;
};

/**
 * Distance from ``mark_price`` to ``liquidation_price`` as a
 * percentage of mark. Returns ``null`` when the position has no
 * liquidation price (e.g. zero-leverage positions or missing data)
 * or when mark is zero, which would otherwise divide by zero.
 *
 * Accepts any shape with the two fields — ``CoinPositionItem`` and
 * ``PositionItem`` both satisfy it — so callers don't need to
 * pick one of two near-identical local helpers.
 */
export function liquidationDistancePct(
  p: PositionWithLiq | CoinPositionItem | PositionItem,
): number | null {
  if (p.liquidation_price == null || p.mark_price === 0) return null;
  return (Math.abs(p.mark_price - p.liquidation_price) / p.mark_price) * 100;
}

/**
 * Render a leverage value with its type suffix (``5x cross``).
 * Returns an em-dash when leverage is not known.
 */
export function formatLeverage(value: number | null, type: string | null): string {
  if (value == null) return "—";
  const base = `${value.toFixed(1)}x`;
  return type == null ? base : `${base} ${type}`;
}
