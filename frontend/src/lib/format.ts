/** Pure formatting helpers (no React) — unit-tested with Vitest. */

export function humanSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** Build a start/end query-string fragment for range-based endpoints. */
export function rangeQuery(start?: number, end?: number): string {
  let s = "";
  if (start != null) s += `&start=${start}`;
  if (end != null) s += `&end=${end}`;
  return s;
}

export function formatHz(hz: number): string {
  if (hz >= 1000) return `${(hz / 1000).toFixed(2)} kHz`;
  return `${hz.toFixed(1)} Hz`;
}
