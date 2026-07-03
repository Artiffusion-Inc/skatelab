/**
 * Shared format-decimal parser for metric rendering.
 *
 * The backend `metrics_registry.py` emits Python format-specs like ".0f",
 * ".1f", ".2f", ".3f" — the number before "f" is the decimal count. This
 * helper parses that string into a JS-friendly integer (default 2).
 *
 * #495 fix: extracted from personal-records.tsx (#446) and applied to
 * MetricCard + MetricDeepDive + TrendChart, all of which had
 * re-invented their own (wrong) decimal heuristic. Single source of
 * truth — every metric renderer in the app uses this helper.
 */
export function parseFormatDecimals(format: string | undefined | null): number {
  const match = format?.match(/(\d+)(?=f)/)
  return match ? Number(match[1]) : 2
}
