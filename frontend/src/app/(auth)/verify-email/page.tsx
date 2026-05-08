"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { type FormEvent, useState } from "react"
import { toast } from "sonner"
import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { verifyEmail } from "@/lib/auth"

export default function VerifyEmailPage() {
  const searchParams = useSearchParams()
  const tokenFromUrl = searchParams.get("token") ?? ""
  const t = useTranslations("auth")
  const [token, setToken] = useState(tokenFromUrl)
  const [loading, setLoading] = useState(false)
  const [verified, setVerified] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!token.trim()) {
      toast.error(t("tokenRequired"), { duration: 3000 })
      return
    }
    setLoading(true)
    try {
      await verifyEmail(token.trim())
      setVerified(true)
      toast.success(t("verifySuccess"), { duration: 3000 })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("verifyError"), { duration: 3000 })
    } finally {
      setLoading(false)
    }
  }

  if (verified) {
    return (
      <div className="space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="nike-h1">{t("verifySuccessTitle")}</h1>
          <p className="text-sm text-muted-foreground">{t("verifySuccessSubtitle")}</p>
        </div>
        <Link href="/login">
          <Button className="w-full">{t("signInBtn")}</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <h1 className="nike-h1">{t("verifyEmail")}</h1>
        <p className="text-sm text-muted-foreground">{t("verifyEmailSubtitle")}</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormField
          label={t("token")}
          id="token"
          type="text"
          required
          value={token}
          onChange={e => setToken(e.target.value)}
          placeholder={t("tokenPlaceholder")}
        />
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("verifying") : t("verifyBtn")}
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        {t("noVerificationCode")}{" "}
        <Link href="/resend-verification" className="text-link hover:underline">
          {t("resendVerification")}
        </Link>
      </p>
    </div>
  )
}
