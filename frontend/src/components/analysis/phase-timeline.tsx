"use client"

import { useCallback } from "react"
import { useAnalysisStore } from "@/stores/analysis"
import type { PhasesData } from "@/types"

interface PhaseTimelineProps {
  totalFrames: number
  phases: PhasesData | null | undefined
}

export function PhaseTimeline({ totalFrames, phases }: PhaseTimelineProps) {
  const { currentFrame, setCurrentFrame } = useAnalysisStore()

  // Build ordered phase entries for keyboard navigation (must be before any early return)
  const phaseEntries = phases
    ? Object.entries(phases)
        .filter(([, v]) => v != null)
        .map(([key, v]) => ({ key, frame: (v as { frame: number }).frame }))
        .sort((a, b) => a.frame - b.frame)
    : []

  const activePhaseIndex = (() => {
    let idx = 0
    for (let i = 0; i < phaseEntries.length; i++) {
      if (currentFrame >= phaseEntries[i].frame) idx = i
    }
    return idx
  })()

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement> | React.KeyboardEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect()
      let x: number

      if ("clientX" in e) {
        x = e.clientX - rect.left
      } else {
        x = rect.width / 2 // Center for keyboard activation
      }

      const seekPercentage = x / rect.width
      const targetFrame = Math.floor(seekPercentage * totalFrames)

      setCurrentFrame(targetFrame)
    },
    [totalFrames, setCurrentFrame],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault()
        const dir = e.key === "ArrowRight" ? 1 : -1
        const next = Math.max(0, Math.min(phaseEntries.length - 1, activePhaseIndex + dir))
        setCurrentFrame(phaseEntries[next].frame)
      } else if (e.key === "Enter") {
        handleSeek(e)
      }
    },
    [activePhaseIndex, phaseEntries, setCurrentFrame, handleSeek],
  )

  if (!phases) return null

  const percentage = (currentFrame / totalFrames) * 100

  const takeoffPercent = phases.takeoff ? (phases.takeoff.frame / totalFrames) * 100 : null

  const peakPercent = phases.peak ? (phases.peak.frame / totalFrames) * 100 : null

  const landingPercent = phases.landing ? (phases.landing.frame / totalFrames) * 100 : null

  return (
    <div
      className="relative w-full h-12 bg-muted rounded-lg overflow-hidden cursor-pointer"
      onClick={handleSeek}
      onKeyDown={handleKeyDown}
      role="slider"
      aria-valuemin={0}
      aria-valuemax={Math.max(0, phaseEntries.length - 1)}
      aria-valuenow={activePhaseIndex}
      aria-label="Phase timeline"
      tabIndex={0}
    >
      {/* Phase zones */}
      {takeoffPercent !== null && peakPercent !== null && (
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${takeoffPercent}%`,
            right: `${100 - peakPercent}%`,
            backgroundColor: "oklch(var(--score-good) / 0.2)",
          }}
        />
      )}

      {peakPercent !== null && landingPercent !== null && (
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${peakPercent}%`,
            right: `${100 - landingPercent}%`,
            backgroundColor: "oklch(var(--score-mid) / 0.2)",
          }}
        />
      )}

      {landingPercent !== null && (
        <div
          className="absolute top-0 bottom-0"
          style={{ left: `${landingPercent}%`, backgroundColor: "oklch(var(--score-bad) / 0.2)" }}
        />
      )}

      {/* Phase markers */}
      {takeoffPercent !== null && (
        <div
          className="absolute top-0 bottom-0 w-0.5"
          style={{ left: `${takeoffPercent}%`, backgroundColor: "oklch(var(--score-good))" }}
          title="Takeoff"
        />
      )}

      {peakPercent !== null && (
        <div
          className="absolute top-0 bottom-0 w-0.5"
          style={{ left: `${peakPercent}%`, backgroundColor: "oklch(var(--score-mid))" }}
          title="Peak"
        />
      )}

      {landingPercent !== null && (
        <div
          className="absolute top-0 bottom-0 w-0.5"
          style={{ left: `${landingPercent}%`, backgroundColor: "oklch(var(--score-bad))" }}
          title="Landing"
        />
      )}

      {/* Scrubber */}
      <div
        className="absolute top-0 bottom-0 w-1 bg-primary shadow-lg"
        style={{ left: `${percentage}%` }}
      >
        <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-3 h-3 bg-primary rounded-full" />
      </div>

      {/* Frame counter */}
      <div className="absolute bottom-1 right-2 text-xs font-medium text-muted-foreground">
        {currentFrame} / {totalFrames}
      </div>
    </div>
  )
}
