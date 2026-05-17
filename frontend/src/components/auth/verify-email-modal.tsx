"use client"

import { useState } from "react"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import { resendVerification } from "@/lib/auth"
import { useTranslations } from "@/i18n"

interface VerifyEmailModalProps {
  open: boolean
  onClose: () => void
}

export function VerifyEmailModal({ open, onClose }: VerifyEmailModalProps) {
  const { user } = useAuth()
  const t = useTranslations("auth")
  const [sent, setSent] = useState(false)
  const [error, setError] = useState("")

  if (!open || !user) return null

  const handleResend = async () => {
    try {
      await resendVerification(user.email)
      setSent(true)
      setError("")
    } catch {
      setError(t("verifyEmailError") ?? "Не удалось отправить письмо")
    }
  }

  const handleBackdropKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" || e.key === "Enter") onClose()
  }

  return (
    <button
      type="button"
      className="fixed inset-0 z-50 flex cursor-default items-center justify-center bg-black/50"
      onClick={onClose}
      onKeyDown={handleBackdropKeyDown}
      aria-label={t("backToSignIn")}
    >
      <div
        className="mx-4 w-full max-w-sm rounded-2xl bg-background p-6 shadow-xl"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t("verifyEmail")}
      >
        <h2 className="text-lg font-semibold">{t("verifyEmail")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {t("verifyEmailSubtitle")} {user.email}
        </p>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        {sent && <p className="mt-2 text-sm text-green-600">{t("resendSuccess")}</p>}
        <div className="mt-4 flex gap-2">
          <Button onClick={handleResend} variant="outline" className="flex-1">
            {t("resendVerification")}
          </Button>
          <Button onClick={onClose} className="flex-1">
            {t("verifyBtn")}
          </Button>
        </div>
      </div>
    </button>
  )
}
