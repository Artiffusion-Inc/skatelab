"use client"

import { LogOut, Settings, X } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { useAuth } from "@/components/auth-provider"
import { useTranslations } from "@/i18n"

export function SettingsSheet() {
  const t = useTranslations("profile")
  const ts = useTranslations("settings")
  const { logout } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)

  async function handleLogout() {
    setOpen(false)
    await logout()
    router.push("/login")
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center justify-between rounded-xl border border-hairline px-4 py-3 text-sm text-ink-mute transition-colors hover:bg-accent"
      >
        <span className="flex items-center gap-2">
          <Settings className="h-4 w-4" />
          {ts("title")}
        </span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center">
          <button
            type="button"
            className="absolute inset-0"
            style={{ backgroundColor: "oklch(var(--background) / 0.5)" }}
            onClick={() => setOpen(false)}
            aria-label="Close settings modal"
          />
          <div className="relative w-full max-w-lg rounded-t-2xl border-t border-hairline bg-background p-5 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="sh-display-md">{ts("title")}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1 text-ink-mute hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-6">
              <button
                type="button"
                onClick={handleLogout}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-destructive/30 px-4 py-3 text-sm text-destructive transition-colors hover:bg-destructive/10"
              >
                <LogOut className="h-4 w-4" />
                {t("signOut")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
