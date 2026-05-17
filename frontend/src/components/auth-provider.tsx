"use client"

import { useRouter } from "next/navigation"
import { createContext, type ReactNode, useContext, useState } from "react"
import { devMockAuth, isDevelopment } from "@/lib/env"
import type { UserResponse } from "@/lib/auth"
import * as auth from "@/lib/auth"
import { clearTokens, getAccessToken, getRefreshToken } from "@/lib/api-client"
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

    auth
      .fetchMe()
      .then(u => setUser(u))
      .catch(() => {
        clearTokens()
        router.push("/login")
      })
      .finally(() => setIsLoading(false))
  })

  async function login(email: string, password: string) {
    const tokens = await auth.login({ email, password })
    auth.setTokens(tokens.access_token, tokens.refresh_token)
    const u = await auth.fetchMe()
    setUser(u)
  }

  async function register(email: string, password: string, displayName?: string) {
    const tokens = await auth.register({ email, password, display_name: displayName })
    auth.setTokens(tokens.access_token, tokens.refresh_token)
    const u = await auth.fetchMe()
    setUser(u)
    router.push("/feed")
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
