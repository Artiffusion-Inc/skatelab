"use client"

import Link from "next/link"
import { type FormEvent, useState } from "react"
import { toast } from "sonner"
import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { resendVerification } from "@/lib/auth"

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function ResendVerificationPage() {
  const t = useTranslations("auth")
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!EMAIL_RE.test(email)) {
      toast.error(t("invalidEmail"), { duration: 3000 })
      return
    }
    setLoading(true)
    try {
      await resendVerification(email)
      setSent(true)
      toast.success(t("resendSuccess"), { duration: 3000 })
    } catch {
      toast.success(t("resendSuccess"), { duration: 3000 })
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="nike-h1">{t("resendSuccessTitle")}</h1>
          <p className="text-sm text-muted-foreground">{t("resendSuccessSubtitle")}</p>
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
        <h1 className="nike-h1">{t("resendVerification")}</h1>
        <p className="text-sm text-muted-foreground">{t("resendVerificationSubtitle")}</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormField
          label="Email"
          id="email"
          type="email"
          required
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("sending") : t("resendBtn")}
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        <Link href="/login" className="text-link hover:underline">
          {t("backToSignIn")}
        </Link>
      </p>
    </div>
  )
}
