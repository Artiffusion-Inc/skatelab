"use client"

import { useState } from "react"
import { useTranslations } from "@/i18n"

export type ViewMode = "self" | "students"

const STORAGE_KEY = "coach_view_mode"

interface CoachViewSwitcherProps {
  mode?: ViewMode
  onModeChange?: (mode: ViewMode) => void
}

export function CoachViewSwitcher({ mode: controlledMode, onModeChange }: CoachViewSwitcherProps) {
  const t = useTranslations("coach")
  const [internalMode, setInternalMode] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return "self"
    return (localStorage.getItem(STORAGE_KEY) as ViewMode) ?? "self"
  })

  const mode = controlledMode ?? internalMode

  const handleSwitch = (next: ViewMode) => {
    setInternalMode(next)
    localStorage.setItem(STORAGE_KEY, next)
    onModeChange?.(next)
  }

  return (
    <div className="flex rounded-lg border border-hairline p-0.5" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={mode === "self"}
        onClick={() => handleSwitch("self")}
        className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none ${
          mode === "self" ? "bg-muted text-ink" : "text-ink-mute"
        }`}
      >
        {t("viewSelf")}
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "students"}
        onClick={() => handleSwitch("students")}
        className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none ${
          mode === "students" ? "bg-muted text-ink" : "text-ink-mute"
        }`}
      >
        {t("viewStudents")}
      </button>
    </div>
  )
}
