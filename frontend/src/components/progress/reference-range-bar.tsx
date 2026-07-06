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

  // #834: do NOT clamp the value marker to [0,100]. Clamping collapsed every
  // out-of-range reading onto the bar's edge, so a catastrophic miss (value=20,
  // ideal 300–600) and a near-miss (value=299) rendered at the same left pixel
  // — the magnitude of the failure was invisible. Let the marker sit at its
  // true position; overflow-visible lets it draw past the bar edge so a 2×
  // overshoot is visibly further out than a 1.5× overshoot. Only the ideal-range
  // band is geometrically clamped (it's a fill rectangle, not a marker).
  const pct = (v: number) => ((v - min) / range) * 100
  const clampBand = (v: number) => Math.min(100, Math.max(0, v))

  const valuePct = pct(value)
  const idealLowPct = clampBand(pct(idealLow))
  const idealHighPct = clampBand(pct(idealHigh))

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
    // overflow-visible: the value marker may sit past the bar edges when the
    // reading is outside [min, max]. The ideal band fill is clamped inside.
    <div
      className="relative h-6 w-full overflow-visible rounded-full bg-muted"
      role="img"
      aria-label={`Value: ${value}, ideal range: ${idealLow}-${idealHigh}`}
    >
      {/* Ideal range band (clamped inside the bar) */}
      <div
        className="absolute top-0 h-full rounded-full bg-green-500/20"
        style={{ left: `${idealLowPct}%`, width: `${idealHighPct - idealLowPct}%` }}
      />
      {/* User value marker — positioned at its true (possibly off-bar) % */}
      <div
        className={`absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full ${markerColor}`}
        style={{ left: `${valuePct}%` }}
      />
    </div>
  )
}
