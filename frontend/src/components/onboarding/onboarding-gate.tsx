"use client"

import { useState } from "react"
import Link from "next/link"
import { fetchMe } from "@/lib/auth"
import { useMountEffect } from "@/lib/useMountEffect"
import { useTranslations } from "@/i18n"
import { X } from "lucide-react"

export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations("onboarding")
  const [showBanner, setShowBanner] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useMountEffect(() => {
    const localCompleted = localStorage.getItem("onboarding_completed")
    if (localCompleted) return

    // Fallback: check backend profile
    const check = async () => {
      try {
        const user = await fetchMe()
        if (user.onboarding_role) {
          localStorage.setItem("onboarding_completed", "true")
          localStorage.setItem("onboarding_role", user.onboarding_role)
          return
        }
      } catch {
        // ignore
      }

      setShowBanner(true)
    }

    check()
  })

  const visible = showBanner && !dismissed

  return (
    <>
      {visible && (
        <div className="flex items-center justify-between gap-3 border-b border-primary/20 bg-primary/5 px-4 py-2.5 text-sm">
          <Link
            href="/onboarding"
            className="font-medium text-primary hover:text-primary/80 transition-colors"
          >
            {t("bannerMessage")}
          </Link>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="shrink-0 rounded-md p-1 text-ink-mute hover:text-foreground transition-colors"
            aria-label={t("bannerDismiss")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {children}
    </>
  )
}
