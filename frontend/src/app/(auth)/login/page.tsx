"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { type FormEvent, useState } from "react"
import { toast } from "sonner"
import { useAuth } from "@/components/auth-provider"
import { FormField } from "@/components/form-field"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { useKeyedEffect } from "@/lib/useMountEffect"

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function LoginPage() {
  const router = useRouter()
  const { login, isAuthenticated, isLoading } = useAuth()
  const t = useTranslations("auth")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)

  // #470: key on isAuthenticated — the async fetchMe() in AuthProvider resolves
  // AFTER mount, flipping isAuthenticated false→true. A mount-only effect
  // captures the stale initial false and the redirect never fires; a keyed
  // effect re-runs when isAuthenticated flips so a logged-in user is redirected.
  useKeyedEffect(() => {
    if (isAuthenticated) router.push("/feed")
  }, [isAuthenticated, router])

  if (isLoading) return null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!EMAIL_RE.test(email)) {
      toast.error(t("invalidEmail"), { duration: 3000 })
      return
    }
    if (!password) {
      toast.error(t("passwordRequired"), { duration: 3000 })
      return
    }
    setLoading(true)
    try {
      await login(email, password)
      toast.success(t("signInSuccess"), { duration: 3000 })
      router.push("/feed")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("signInError"), { duration: 3000 })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <h1 className="sh-display-lg text-ink">{t("signIn")}</h1>
        <p className="sh-caption text-ink-mute">{t("signInSubtitle")}</p>
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
          label={t("password")}
          id="password"
          type="password"
          required
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
        />
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("signingIn") : t("signInBtn")}
        </Button>
      </form>
      <p className="text-center sh-caption text-ink-mute">
        {t("noAccount")}{" "}
        <Link href="/register" className="text-link hover:underline">
          {t("register")}
        </Link>
      </p>
    </div>
  )
}
