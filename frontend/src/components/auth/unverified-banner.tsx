"use client"

import { useAuth } from "@/components/auth-provider"
import { useTranslations } from "@/i18n"
import { AlertTriangle } from "lucide-react"

export function UnverifiedBanner() {
  const { user } = useAuth()
  const t = useTranslations("auth")
  if (!user || user.is_verified) return null

  return (
    <div className="border-b border-yellow-500/20 bg-yellow-500/5 px-4 py-2">
      <p className="mx-auto max-w-2xl text-center text-sm text-yellow-700 dark:text-yellow-400">
        <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" />
        {t("unverifiedBanner")}
      </p>
    </div>
  )
}
