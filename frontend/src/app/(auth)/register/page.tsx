"use client"

import { Eye, EyeOff } from "lucide-react"
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

export default function RegisterPage() {
  const router = useRouter()
  const { register, isAuthenticated, isLoading } = useAuth()
  const t = useTranslations("auth")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  // #470: key on isAuthenticated — see login/page.tsx. Mount-only effect would
  // capture the stale initial false and never redirect a logged-in user.
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
    if (password.length < 8) {
      toast.error(t("passwordTooShort"), { duration: 3000 })
      return
    }
    setLoading(true)
    try {
      await register(email, password)
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
        <div className="space-y-1.5">
          <label htmlFor="password" className="sh-caption font-medium text-ink">
            {t("password")}
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={t("passwordPlaceholder")}
              className="w-full rounded-md border border-hairline bg-background px-3 py-2.5 pr-10 text-sm transition-colors duration-200 placeholder:text-ink-faint focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword(s => !s)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-mute hover:text-ink transition-colors"
              aria-label={showPassword ? t("hidePassword") : t("showPassword")}
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
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
