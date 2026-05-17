"use client"

import { useState, useCallback } from "react"
import { useTranslations } from "@/i18n"
import { useMountEffect } from "@/lib/useMountEffect"
import { cn } from "@/lib/utils"
import type { UserRole } from "./onboarding-flow"

const ROLE_KEYS: { id: UserRole; labelKey: string; descKey: string }[] = [
  { id: "skater", labelKey: "roles.skater.label", descKey: "roles.skater.description" },
  { id: "coach", labelKey: "roles.coach.label", descKey: "roles.coach.description" },
  {
    id: "choreographer",
    labelKey: "roles.choreographer.label",
    descKey: "roles.choreographer.description",
  },
]

interface FirstAnalysisCelebrationProps {
  hasSessions?: boolean
}

export function FirstAnalysisCelebration({ hasSessions = false }: FirstAnalysisCelebrationProps) {
  const t = useTranslations("onboarding")
  const [visible, setVisible] = useState(false)
  const [selectedRole, setSelectedRole] = useState<UserRole | null>(null)

  useMountEffect(() => {
    const completed = localStorage.getItem("has_completed_first_analysis")
    if (completed === null && hasSessions) {
      setVisible(true)
    }
  })

  const handleSave = useCallback(() => {
    if (selectedRole) {
      localStorage.setItem("onboarding_role", selectedRole)
      localStorage.setItem("onboarding_completed", "true")
    }
    localStorage.setItem("has_completed_first_analysis", "true")
    setVisible(false)
  }, [selectedRole])

  const handleSkip = useCallback(() => {
    localStorage.setItem("has_completed_first_analysis", "true")
    setVisible(false)
  }, [])

  if (!visible) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={t("celebrationTitle")}
    >
      <div className="mx-4 w-full max-w-md rounded-2xl border border-hairline bg-card p-6 shadow-lg">
        <h2 className="mb-2 text-center text-xl font-medium text-foreground">
          {t("celebrationTitle")}
        </h2>
        <p className="mb-6 text-center text-sm text-ink-mute">{t("celebrationSubtitle")}</p>

        <div className="space-y-2">
          {ROLE_KEYS.map(role => (
            <button
              type="button"
              key={role.id}
              onClick={() => setSelectedRole(role.id)}
              className={cn(
                "w-full rounded-xl border p-4 text-left transition-all duration-200",
                selectedRole === role.id
                  ? "border-primary bg-primary/5"
                  : "border-hairline bg-card hover:bg-accent",
              )}
            >
              <p className="text-sm font-medium text-foreground">{t(role.labelKey)}</p>
              <p className="mt-0.5 text-xs text-ink-mute">{t(role.descKey)}</p>
            </button>
          ))}
        </div>

        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={!selectedRole}
            className="h-11 w-full rounded-full bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {t("continue")}
          </button>
          <button
            type="button"
            onClick={handleSkip}
            className="h-10 w-full text-sm text-ink-mute hover:text-foreground transition-colors"
          >
            {t("skip")}
          </button>
        </div>
      </div>
    </div>
  )
}
