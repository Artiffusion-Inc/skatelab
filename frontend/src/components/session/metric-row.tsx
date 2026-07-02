"use client"

import { MetricBadge } from "./metric-badge"

interface MetricRowProps {
  name: string
  label: string
  value: number
  unit?: string
  /** Backend registry format spec (e.g. ".3f", ".0f"). Parsed for decimal
   * count; defaults to 2 decimals when absent (#510, #446/#495 class). */
  format?: string | null
  isInRange?: boolean | null
  isPr?: boolean
  prevBest?: number | null
  refRange?: [number, number] | null
  direction?: "higher" | "lower"
}

/** Decimal count from a backend format spec like ".3f" / ".0f" / ".1f".
 * Mirrors personal-records.tsx:47 (#446). Defaults to 2. */
function decimalsFromFormat(format: string | null | undefined): number {
  return Number(format?.match(/\d+(?=f)/)?.[0] ?? 2)
}

function rangeColor(inRange: boolean | null | undefined): string {
  if (inRange === null || inRange === undefined) return "text-muted-foreground"
  return "" // color set via style prop
}

function rangeStyle(inRange: boolean | null | undefined) {
  if (inRange === null || inRange === undefined) return undefined
  return { color: inRange ? "oklch(var(--score-good))" : "oklch(var(--score-bad))" }
}

export function MetricRow({
  label,
  value,
  unit,
  format,
  isInRange,
  isPr,
  prevBest,
}: MetricRowProps) {
  const delta = isPr && prevBest != null ? value - prevBest : null
  const deltaStr = delta !== null ? `${delta >= 0 ? "+" : ""}${delta.toFixed(3)}` : null
  const decimals = decimalsFromFormat(format)

  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <div>
        <span className="text-sm">{label}</span>
        {deltaStr && <MetricBadge text={deltaStr} />}
      </div>
      <span className={`text-sm font-mono ${rangeColor(isInRange)}`} style={rangeStyle(isInRange)}>
        {value.toFixed(decimals)} {unit}
      </span>
    </div>
  )
}
