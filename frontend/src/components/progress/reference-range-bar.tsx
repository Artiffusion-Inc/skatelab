interface ReferenceRangeBarProps {
  value: number
  min: number
  max: number
  idealLow: number
  idealHigh: number
  direction: "higher" | "lower"
}

export function ReferenceRangeBar({
  value,
  min,
  max,
  idealLow,
  idealHigh,
  direction,
}: ReferenceRangeBarProps) {
  const range = max - min
  if (range === 0) return null

  const clamp = (v: number) => Math.min(100, Math.max(0, v))
  const pct = (v: number) => clamp(((v - min) / range) * 100)

  const valuePct = pct(value)
  const idealLowPct = pct(idealLow)
  const idealHighPct = pct(idealHigh)

  // Color the value marker based on whether it falls in the ideal range
  const inRange = value >= idealLow && value <= idealHigh
  const markerColor = inRange
    ? "bg-green-500"
    : direction === "higher"
      ? value < idealLow
        ? "bg-orange-500"
        : "bg-primary"
      : value > idealHigh
        ? "bg-orange-500"
        : "bg-primary"

  return (
    <div
      className="relative h-6 w-full rounded-full bg-muted"
      role="img"
      aria-label={`Value: ${value}, ideal range: ${idealLow}-${idealHigh}`}
    >
      {/* Ideal range */}
      <div
        className="absolute top-0 h-full rounded-full bg-green-500/20"
        style={{ left: `${idealLowPct}%`, width: `${idealHighPct - idealLowPct}%` }}
      />
      {/* User value */}
      <div
        className={`absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full ${markerColor}`}
        style={{ left: `${valuePct}%` }}
      />
    </div>
  )
}
