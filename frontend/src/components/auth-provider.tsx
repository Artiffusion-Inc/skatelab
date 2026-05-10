"use client"

import { useRouter } from "next/navigation"
import { createContext, type ReactNode, useContext, useState } from "react"
import { devMockAuth, isDevelopment } from "@/lib/env"
import type { UserResponse } from "@/lib/auth"
import * as auth from "@/lib/auth"
import { clearTokens, getAccessToken, getRefreshToken } from "@/lib/api-client"
import { isPublicPage } from "@/lib/is-public-page"
import { useMountEffect } from "@/lib/useMountEffect"

interface AuthContextValue {
  user: UserResponse | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function needsVerificationRedirect(user: UserResponse): boolean {
  if (user.is_verified) return false
  if (typeof window === "undefined") return false
  const path = window.location.pathname
  return !path.startsWith("/verify-email") && !path.startsWith("/resend-verification")
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const [user, setUser] = useState<UserResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)

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

    const hasToken = getAccessToken() || getRefreshToken()
    if (!hasToken) {
      setIsLoading(false)
      return
    }

    const publicPage = typeof window !== "undefined" && isPublicPage(window.location.pathname)

    auth
      .fetchMe()
      .then(u => {
        setUser(u)
        if (needsVerificationRedirect(u)) {
          router.push("/verify-email")
        }
      })
      .catch(() => {
        clearTokens()
        if (!publicPage) router.push("/login")
      })
      .finally(() => setIsLoading(false))
  })

  async function login(email: string, password: string) {
    const tokens = await auth.login({ email, password })
    auth.setTokens(tokens.access_token, tokens.refresh_token)
    const u = await auth.fetchMe()
    setUser(u)
    if (needsVerificationRedirect(u)) {
      router.push("/verify-email")
    }
  }

  async function register(email: string, password: string, displayName?: string) {
    const tokens = await auth.register({ email, password, display_name: displayName })
    auth.setTokens(tokens.access_token, tokens.refresh_token)
    const u = await auth.fetchMe()
    setUser(u)
    router.push("/verify-email")
  }

  async function logout() {
    await auth.logout()
    setUser(null)
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
