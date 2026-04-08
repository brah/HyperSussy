/**
 * Number and string formatting helpers.
 *
 * Mirrors the Python helpers in formatting.py and navigation.py.
 */

/** Format a dollar price with smart decimal precision. */
export function formatPrice(value: number): string {
  if (value === 0) return "$0.00";
  const negative = value < 0;
  const v = Math.abs(value);
  let result: string;
  if (v >= 1.0) {
    result = `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  } else {
    const leadingZeros = Math.max(0, Math.floor(-Math.log10(v)));
    const decimals = leadingZeros + 2;
    result = `$${v.toFixed(decimals)}`;
  }
  return negative ? `-${result}` : result;
}

/** Format a large USD amount with K/M/B suffix. */
export function formatUSD(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

/** Format a funding rate as a percentage string. */
export function formatFundingRate(rate: number): string {
  return `${(rate * 100).toFixed(4)}%`;
}

/** Format a position size with fixed decimals. */
export function formatSize(value: number, decimals = 4): string {
  return value.toFixed(decimals);
}

/** Format a percentage value (already in 0-100 range) with a % suffix. */
export function formatPercent(value: number, decimals = 2): string {
  return `${value.toFixed(decimals)}%`;
}

/** Format a byte count using binary (1024) units. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

/** Format an integer count compactly with k/M/B suffixes (e.g. 12.3k, 1.21M). */
export function formatCount(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e4) return `${sign}${(abs / 1e3).toFixed(1)}k`;
  if (abs >= 1e3) return `${sign}${abs.toLocaleString("en-US")}`;
  return `${sign}${abs}`;
}

/** Shorten a 0x address to prefix..suffix form (e.g. "0xab4f..ef35"). */
export function shortAddress(address: string, chars = 4): string {
  if (address.length <= 2 + chars * 2) return address;
  const prefix = address.slice(0, 2 + chars);
  const suffix = address.slice(-chars);
  return `${prefix}..${suffix}`;
}

/** Validate a 0x wallet address string. */
export function isValidAddress(value: string): boolean {
  if (value.length !== 42 || !value.startsWith("0x")) return false;
  return /^[0-9a-fA-F]+$/.test(value.slice(2));
}

/** Normalize a 0x address to lowercase. */
export function normalizeAddress(value: string): string | null {
  const trimmed = value.trim();
  if (!isValidAddress(trimmed)) return null;
  return `0x${trimmed.slice(2).toLowerCase()}`;
}
