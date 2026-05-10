"use client"

import { useState } from "react"
import { toast } from "sonner"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { updateSettings } from "@/lib/auth"
import { useRouter } from "next/navigation"

export function SettingsForm() {
  const t = useTranslations("settings")
  const tc = useTranslations("common")
  const { user } = useAuth()
  const router = useRouter()

  const [language, setLanguage] = useState(user?.language ?? "ru")
  const [timezone, setTimezone] = useState(user?.timezone ?? "Europe/Moscow")
  const [theme, setTheme] = useState(user?.theme ?? "system")
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await updateSettings({ language, timezone, theme: theme as "light" | "dark" | "system" })
      toast.success(t("saved"))
    } catch {
      toast.error(t("saveError"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-md space-y-4 p-6">
      <h1 className="sh-heading-lg">{t("title")}</h1>

      <div className="space-y-1.5">
        <label htmlFor="language" className="text-sm font-medium">
          {t("language")}
        </label>
        <select
          id="language"
          value={language}
          onChange={e => setLanguage(e.target.value)}
          className="w-full rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm"
        >
          <option value="ru">Русский</option>
          <option value="en">English</option>
        </select>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="timezone" className="text-sm font-medium">
          {t("timezone")}
        </label>
        <select
          id="timezone"
          value={timezone}
          onChange={e => setTimezone(e.target.value)}
          className="w-full rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm"
        >
          <option value="Europe/Moscow">Europe/Moscow</option>
          <option value="Europe/London">Europe/London</option>
          <option value="America/New_York">America/New_York</option>
        </select>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="theme" className="text-sm font-medium">
          {t("theme")}
        </label>
        <select
          id="theme"
          value={theme}
          onChange={e => setTheme(e.target.value)}
          className="w-full rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm"
        >
          <option value="system">{t("system")}</option>
          <option value="light">{t("light")}</option>
          <option value="dark">{t("dark")}</option>
        </select>
      </div>

      <Button type="submit" disabled={saving} className="w-full">
        {saving ? tc("saving") : t("save")}
      </Button>

      <div className="border-t border-hairline pt-4">
        <h2 className="mb-3 text-sm font-medium">{t("onboardingTitle")}</h2>
        <p className="mb-3 text-xs text-ink-mute">{t("onboardingHint")}</p>
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => {
            localStorage.removeItem("onboarding_completed")
            router.push("/onboarding")
          }}
        >
          {t("restartOnboarding")}
        </Button>
      </div>
    </form>
  )
}
