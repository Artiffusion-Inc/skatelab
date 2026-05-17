"use client"

import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/lib/utils"

interface MetricCardProps {
  label: string
  value: number
  unit: string
  direction?: "higher" | "lower"
  trend?: "improving" | "stable" | "declining"
  isPr?: boolean
  isWarning?: boolean
  onClick?: () => void
}

export function MetricCard({
  label,
  value,
  unit,
  direction,
  trend,
  isPr,
  isWarning,
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
        <span className="text-xl font-semibold">
          {value.toFixed(direction === "lower" ? 1 : 2)}
        </span>
        <span className="text-xs text-ink-mute">{unit}</span>
        {trend && <TrendIcon className={cn("ml-auto h-4 w-4", trendColor)} />}
      </div>
      {isPr && <span className="mt-1 text-[10px] font-bold text-green-600">PR</span>}
      {isWarning && <span className="mt-1 text-[10px] font-bold text-yellow-600">!</span>}
    </button>
  )
}
