/**
 * Merge two timestamp-keyed series into a single array for recharts.
 *
 * Performs a full outer join on nearest-5-minute bucket so both series'
 * timestamps appear in the output. The primary series' fields are spread
 * verbatim; the secondary series contributes one extra key (`destKey`).
 *
 * 5-minute buckets are used because our OI/funding snapshots are polled every
 * ~5 minutes. Within a bucket, the latest reading wins so no data is silently
 * dropped when feeds are slightly offset.
 */
export function mergeTimeSeries<
  A extends { timestamp_ms: number },
  B extends { timestamp_ms: number },
>(
  a: A[],
  b: B[],
  srcKey: keyof B,
  destKey: string,
): Array<A & Record<string, number | undefined>> {
  const BUCKET_MS = 5 * 60_000;

  // Build lookup for b: bucket → value (latest wins on collision)
  const bucketB = new Map<number, number>();
  for (const item of b) {
    const bucket = Math.round(item.timestamp_ms / BUCKET_MS);
    bucketB.set(bucket, item[srcKey] as unknown as number);
  }

  // Build lookup for a: bucket → item (latest wins on collision)
  const bucketA = new Map<number, A>();
  for (const item of a) {
    const bucket = Math.round(item.timestamp_ms / BUCKET_MS);
    bucketA.set(bucket, item);
  }

  // Union of all buckets, sorted ascending
  const allBuckets = Array.from(
    new Set([...bucketA.keys(), ...bucketB.keys()]),
  ).sort((x, y) => x - y);

  return allBuckets.map((bucket) => {
    const aItem = bucketA.get(bucket);
    const bVal = bucketB.get(bucket);
    if (aItem != null) {
      return { ...aItem, [destKey]: bVal };
    }
    // b-only bucket: synthesise a minimal A-shaped record with timestamp
    return {
      timestamp_ms: bucket * BUCKET_MS,
      [destKey]: bVal,
    } as A & Record<string, number | undefined>;
  });
}
