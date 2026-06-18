"use client"

import { useCallback } from "react"
import { useAnalysisStore } from "@/stores/analysis"
import type { PhaseDetectionResult, PhaseExtended } from "@/types"

interface PhaseTimelineExtendedProps {
  totalFrames: number
  result: PhaseDetectionResult | null | undefined
}

const PHASE_COLORS: Record<PhaseExtended["name"], string> = {
  approach: "oklch(var(--score-mid) / 0.3)",
  takeoff: "oklch(var(--score-good) / 0.3)",
  air: "oklch(var(--primary) / 0.3)",
  landing: "oklch(var(--score-bad) / 0.3)",
  glide_out: "oklch(var(--score-mid) / 0.2)",
}

const PHASE_LABELS_RU: Record<PhaseExtended["name"], string> = {
  approach: "Заход",
  takeoff: "Взлёт",
  air: "Полёт",
  landing: "Приземление",
  glide_out: "Выезд",
}

export function PhaseTimelineExtended({ totalFrames, result }: PhaseTimelineExtendedProps) {
  const { currentFrame, setCurrentFrame } = useAnalysisStore()

  const handleSeek = useCallback(
    (e: { currentTarget: HTMLElement; clientX: number }) => {
      const rect = e.currentTarget.getBoundingClientRect()
      const x = e.clientX - rect.left
      const seekPercentage = x / rect.width
      const targetFrame = Math.floor(seekPercentage * totalFrames)
      setCurrentFrame(Math.max(0, Math.min(targetFrame, totalFrames - 1)))
    },
    [totalFrames, setCurrentFrame],
  )

  if (!result?.phases || result.phases.length === 0) return null

  const percentage = (currentFrame / totalFrames) * 100

  return (
    <div
      className="relative w-full h-12 bg-muted rounded-lg overflow-hidden cursor-pointer"
      onClick={handleSeek}
      onKeyDown={e => {
        if (e.key === "ArrowLeft") {
          e.preventDefault()
          setCurrentFrame(Math.max(0, currentFrame - 1))
        } else if (e.key === "ArrowRight") {
          e.preventDefault()
          setCurrentFrame(Math.min(totalFrames - 1, currentFrame + 1))
        }
      }}
      role="slider"
      aria-valuemin={0}
      aria-valuemax={totalFrames}
      aria-valuenow={currentFrame}
      aria-label="Phase timeline"
      tabIndex={0}
    >
      {/* Phase zones */}
      {result.phases.map((phase, _index) => {
        const startPercent = (phase.start_frame / totalFrames) * 100
        const endPercent = (phase.end_frame / totalFrames) * 100
        const isLowConfidence = phase.confidence < 0.5

        return (
          <div
            key={phase.name}
            className="absolute top-0 bottom-0 group"
            style={{
              left: `${startPercent}%`,
              width: `${endPercent - startPercent}%`,
              backgroundColor: PHASE_COLORS[phase.name],
            }}
            title={`${PHASE_LABELS_RU[phase.name]}: ${phase.confidence.toFixed(2)} confidence`}
          >
            {/* Warning stripe for low confidence */}
            {isLowConfidence && (
              <div className="absolute inset-0 bg-[repeating-linear-gradient(45deg,transparent,transparent_8px,oklch(var(--score-bad)/0.3)_8px,oklch(var(--score-bad)/0.3)_16px)]" />
            )}

            {/* Phase label (visible on hover or wide enough) */}
            {endPercent - startPercent > 8 && (
              <span className="absolute top-1 left-1 text-[9px] text-foreground/70 truncate pointer-events-none">
                {PHASE_LABELS_RU[phase.name]}
              </span>
            )}

            {/* Tooltip on hover */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10">
              <div className="bg-popover text-popover-foreground text-xs rounded-md px-2 py-1 shadow-lg whitespace-nowrap">
                {PHASE_LABELS_RU[phase.name]}: {phase.start_time.toFixed(2)}s -{" "}
                {phase.end_time.toFixed(2)}s
                <br />
                Confidence: {(phase.confidence * 100).toFixed(0)}%
              </div>
            </div>
          </div>
        )
      })}

      {/* Current frame marker */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-foreground z-10"
        style={{ left: `${percentage}%` }}
      >
        <div className="absolute -top-1 -translate-x-1/2 w-2 h-2 bg-foreground rounded-full" />
      </div>
    </div>
  )
}
