"use client"

import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/lib/utils"
import { parseFormatDecimals } from "@/lib/format"

interface MetricCardProps {
  label: string
  value: number
  unit: string
  trend?: "improving" | "stable" | "declining"
  isPr?: boolean
  isWarning?: boolean
  // #835: when false the metric has no recorded PR yet — render an empty
  // state instead of "0.00 deg/s". Pre-fix the card rendered value (which
  // defaulted to 0 upstream when no PR existed) as a bold measurement,
  // making "no data yet" indistinguishable from a real zero reading.
  hasData?: boolean
  // #495: format prop is the backend's Python format-spec (e.g. ".0f" for
  // rotation_speed=540, ".2f" for airtime=0.85). The component uses
  // parseFormatDecimals to derive the decimal count from this string
  // (single source of truth from metrics_registry.py). Pre-fix the
  // component hardcoded decimals based on a `direction` prop (removed
  // in #495 — direction-based decimal heuristics were wrong by design
  // for the backend's per-metric format spec).
  format?: string
  onClick?: () => void
}

export function MetricCard({
  label,
  value,
  unit,
  trend,
  isPr,
  isWarning,
  hasData = true,
  format,
  onClick,
}: MetricCardProps) {
  const TrendIcon =
    trend === "improving" ? TrendingUp : trend === "declining" ? TrendingDown : Minus
  const trendColor =
    trend === "improving"
      ? "text-green-600"
      : trend === "declining"
        ? "text-red-600"
        : "text-ink-mute"

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border border-hairline p-3 text-left transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        isWarning && "border-yellow-500/30 bg-yellow-500/5",
        isPr && "border-green-500/30 bg-green-500/5",
      )}
    >
      <p className="text-xs text-ink-mute">{label}</p>
      <div className="mt-1 flex items-baseline gap-1.5">
        {hasData ? (
          <>
            <span className="text-xl font-semibold">
              {/* #495: use the backend's format spec to derive decimals. */}
              {value.toFixed(parseFormatDecimals(format))}
            </span>
            <span className="text-xs text-ink-mute">{unit}</span>
          </>
        ) : (
          // #835: no PR recorded yet — em-dash placeholder, dimmed. Do not
          // show "0.00" + unit, which read as a measured zero.
          <span className="text-xl font-semibold text-ink-mute">—</span>
        )}
        {trend && hasData && <TrendIcon className={cn("ml-auto h-4 w-4", trendColor)} />}
      </div>
      {isPr && <span className="mt-1 text-[10px] font-bold text-green-600">PR</span>}
      {isWarning && <span className="mt-1 text-[10px] font-bold text-yellow-600">!</span>}
    </button>
  )
}
