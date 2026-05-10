"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { type FormEvent, useState } from "react"
import { toast } from "sonner"
import { useAuth } from "@/components/auth-provider"
import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuth()
  const t = useTranslations("auth")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!EMAIL_RE.test(email)) {
      toast.error(t("invalidEmail"), { duration: 3000 })
      return
    }
    if (password.length < 8) {
      toast.error(t("passwordTooShort"), { duration: 3000 })
      return
    }
    if (password !== confirmPassword) {
      toast.error(t("passwordsMismatch"), { duration: 3000 })
      return
    }
    setLoading(true)
    try {
      await register(email, password, displayName || undefined)
      toast.success(t("signUpSuccess"), { duration: 3000 })
      router.push("/feed")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("signUpError"), { duration: 3000 })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <h1 className="sh-display-lg text-ink">{t("signUp")}</h1>
        <p className="sh-caption text-ink-mute">{t("signUpSubtitle")}</p>
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
        <FormField
          label={t("nameOptional")}
          id="name"
          type="text"
          value={displayName}
          onChange={e => setDisplayName(e.target.value)}
          placeholder={t("namePlaceholder")}
        />
        <FormField
          label={t("password")}
          id="password"
          type="password"
          required
          minLength={8}
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder={t("passwordPlaceholder")}
        />
        <FormField
          label={t("confirmPassword")}
          id="confirm-password"
          type="password"
          required
          value={confirmPassword}
          onChange={e => setConfirmPassword(e.target.value)}
          placeholder={t("passwordPlaceholder")}
        />
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("signingUp") : t("signUpBtn")}
        </Button>
      </form>
      <p className="text-center sh-caption text-ink-mute">
        {t("hasAccount")}{" "}
        <Link href="/login" className="text-link hover:underline">
          {t("signInBtn")}
        </Link>
      </p>
    </div>
  )
}
