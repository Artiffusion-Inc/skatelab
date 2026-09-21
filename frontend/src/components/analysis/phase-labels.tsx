"use client"

import { useTranslations } from "@/i18n"
import type { PhasesData } from "@/types"

interface PhaseLabelsProps {
  phases: PhasesData
  currentFrame: number
  width: number
}

export function PhaseLabels({ phases, currentFrame, width }: PhaseLabelsProps) {
  const t = useTranslations("analysis")
  const hasPhase = phases.takeoff !== null || phases.peak !== null || phases.landing !== null
  if (!hasPhase || currentFrame <= 0) return null

  const phaseLabels = [
    { key: "takeoff", frame: phases.takeoff?.frame ?? null, label: t("phases.takeoff") },
    { key: "peak", frame: phases.peak?.frame ?? null, label: t("phases.air") },
    { key: "landing", frame: phases.landing?.frame ?? null, label: t("phases.landing") },
  ] as const

  return (
    <fieldset className="absolute inset-x-0 top-2 m-0 min-w-0 border-0 p-0 px-4">
      <legend className="sr-only">{t("phaseMarkers")}</legend>
      {phaseLabels.map(({ key, frame, label }) =>
        frame === null ? null : (
          <div
            key={key}
            className="absolute top-0 rounded-full bg-background/90 px-2 py-1 text-xs sh-button-cap text-ink shadow-sm"
            style={{ left: `${(frame / currentFrame) * width}px` }}
          >
            {label}
          </div>
        ),
      )}
    </fieldset>
  )
}
