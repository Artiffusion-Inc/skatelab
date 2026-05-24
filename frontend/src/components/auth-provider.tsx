"use client"

import { useRouter } from "next/navigation"
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react"
import { devMockAuth, isDevelopment } from "@/lib/env"
import type { UserResponse } from "@/lib/auth"
import * as auth from "@/lib/auth"
import { clearTokens } from "@/lib/api-client"
import { useMountEffect } from "@/lib/useMountEffect"
import { useConsent } from "@/components/consent-provider"
import { identifyUser, resetIdentity } from "@/lib/posthog"

interface AuthContextValue {
  user: UserResponse | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const [user, setUser] = useState<UserResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const { hasConsented } = useConsent()
  const prevAnalyticsConsent = useRef(false)

  useMountEffect(() => {
    if (devMockAuth && isDevelopment) {
      setUser({
        id: "dev",
        email: "dev@example.com",
        display_name: "Dev User",
        avatar_url: null,
        bio: null,
        height_cm: null,
        weight_kg: null,
        language: "ru",
        timezone: "Europe/Moscow",
        theme: "system",
        onboarding_role: null,
        is_active: true,
        is_verified: true,
        created_at: new Date().toISOString(),
      })
      setIsLoading(false)
      return
    }

    const hasSession = typeof document !== "undefined" && document.cookie.includes("sb_auth=1")
    if (!hasSession) {
      setIsLoading(false)
      return
    }

    auth
      .fetchMe()
      .then(u => setUser(u))
      .catch(() => {
        clearTokens()
        router.push("/login")
      })
      .finally(() => setIsLoading(false))
  })

  // Re-identify when analytics consent is granted after login
  useEffect(() => {
    const analyticsNow = hasConsented("analytics")
    if (analyticsNow && !prevAnalyticsConsent.current && user) {
      identifyUser(user.id, {
        email: user.email,
        role: user.onboarding_role,
        language: user.language,
        onboarding_completed: user.is_verified,
      })
    }
    prevAnalyticsConsent.current = analyticsNow
  }, [hasConsented, user])

  async function login(email: string, password: string) {
    await auth.login({ email, password })
    // Backend sets httpOnly cookies via Set-Cookie headers.
    // Set sb_auth sentinel for SSR gating.
    // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
    document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax"
    const u = await auth.fetchMe()
    setUser(u)
    if (hasConsented("analytics")) {
      identifyUser(u.id, {
        email: u.email,
        role: u.onboarding_role,
        language: u.language,
        onboarding_completed: u.is_verified,
      })
    }
  }

  async function register(email: string, password: string, displayName?: string) {
    await auth.register({ email, password, display_name: displayName })
    // Backend sets httpOnly cookies via Set-Cookie headers.
    // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
    document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax"
    const u = await auth.fetchMe()
    setUser(u)
    if (hasConsented("analytics")) {
      identifyUser(u.id, {
        email: u.email,
        role: u.onboarding_role,
        language: u.language,
        onboarding_completed: false,
      })
    }
    router.push("/feed")
  }

  async function logout() {
    await auth.logout()
    setUser(null)
    resetIdentity()
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
