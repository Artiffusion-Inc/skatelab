/**
 * Auth API: schemas, cookie-based auth, and endpoint wrappers.
 *
 * Tokens are now httpOnly cookies set by the backend.
 * The frontend only manages the `sb_auth` sentinel cookie.
 */

import { z } from "zod"
import { apiFetch, authFetch, clearTokens } from "@/lib/api-client"

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const RegisterRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(128),
  display_name: z.string().max(100).optional(),
})

export const LoginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.literal("bearer"),
})

export const UserResponseSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  display_name: z.string().nullable(),
  avatar_url: z.string().nullable(),
  bio: z.string().nullable(),
  height_cm: z.number().int().nullable(),
  weight_kg: z.number().nullable(),
  language: z.string(),
  timezone: z.string(),
  theme: z.string(),
  onboarding_role: z.string().nullable(),
  is_active: z.boolean(),
  is_verified: z.boolean(),
  created_at: z.string(),
})

export const UpdateProfileRequestSchema = z.object({
  display_name: z.string().max(100).optional().nullable(),
  bio: z.string().optional().nullable(),
  height_cm: z.number().int().min(50).max(250).optional().nullable(),
  weight_kg: z.number().min(20).max(300).optional().nullable(),
})

export const UpdateSettingsRequestSchema = z.object({
  language: z.string().max(10).optional().nullable(),
  timezone: z.string().max(50).optional().nullable(),
  theme: z.enum(["light", "dark", "system"]).optional().nullable(),
})

export type RegisterRequest = z.infer<typeof RegisterRequestSchema>
export type LoginRequest = z.infer<typeof LoginRequestSchema>
export type TokenResponse = z.infer<typeof TokenResponseSchema>
export type UserResponse = z.infer<typeof UserResponseSchema>
export type UpdateProfileRequest = z.infer<typeof UpdateProfileRequestSchema>
export type UpdateSettingsRequest = z.infer<typeof UpdateSettingsRequestSchema>

// Re-export cookie helpers for consumers
export { clearTokens } from "@/lib/api-client"

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

const JSON_POST = { "Content-Type": "application/json" }

export async function register(data: RegisterRequest): Promise<TokenResponse> {
  return apiFetch("/auth/register", TokenResponseSchema, {
    method: "POST",
    auth: false,
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function login(data: LoginRequest): Promise<TokenResponse> {
  return apiFetch("/auth/login", TokenResponseSchema, {
    method: "POST",
    auth: false,
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function refreshToken(): Promise<TokenResponse> {
  return apiFetch("/auth/refresh", TokenResponseSchema, {
    method: "POST",
    auth: false,
    headers: JSON_POST,
  })
}

export async function logout(): Promise<void> {
  // #826: was raw fetch that swallowed server errors and network failures
  // — clearTokens() ran unconditionally, local state cleared while the
  // server-side refresh token stayed valid (silent session leak). Now use
  // authFetch so a 401 triggers silent refresh and the call actually reaches
  // the revocation endpoint.
  try {
    const res = await authFetch("/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: JSON_POST,
    })
    if (!res.ok) {
      // Surface non-auth failures; caller decides whether to retry. Still
      // clear local state below so the UI is consistent, but the server
      // revocation status is now observable instead of silently dropped.
      console.warn(`logout returned ${res.status}, server session may remain`)
    }
  } catch (e) {
    // Network failure — log so it's not invisible, but proceed to clear local
    // state so the user is logged out client-side.
    console.warn("logout request failed, server session may remain:", e)
  }
  clearTokens()
}

export async function fetchMe(): Promise<UserResponse> {
  return apiFetch("/users/me", UserResponseSchema)
}

export async function updateProfile(data: UpdateProfileRequest): Promise<UserResponse> {
  return apiFetch("/users/me", UserResponseSchema, {
    method: "PATCH",
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function updateSettings(data: UpdateSettingsRequest): Promise<UserResponse> {
  return apiFetch("/users/me/settings", UserResponseSchema, {
    method: "PATCH",
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function updateOnboardingRole(
  role: "skater" | "coach" | "choreographer",
): Promise<UserResponse> {
  return apiFetch("/users/me/onboarding", UserResponseSchema, {
    method: "PATCH",
    headers: JSON_POST,
    body: JSON.stringify({ onboarding_role: role }),
  })
}

// #827: verify/resend return { message } — validate with zod so apiFetch
// (which orchestrates silent refresh on 401) can be used instead of raw fetch.
const MessageResponseSchema = z.object({ message: z.string() })

export async function verifyEmail(token: string): Promise<{ message: string }> {
  // #827: was raw fetch — a 401 (expired access cookie) threw "Verification
  // failed" even though the verification token was valid, because there was
  // no silent refresh. apiFetch with auth:true refreshes on 401 before giving
  // up, so an expired access cookie no longer fails a valid verification.
  return apiFetch("/auth/verify-email", MessageResponseSchema, {
    method: "POST",
    headers: JSON_POST,
    body: JSON.stringify({ token }),
  })
}

export async function resendVerification(email: string): Promise<{ message: string }> {
  return apiFetch("/auth/resend-verification", MessageResponseSchema, {
    method: "POST",
    headers: JSON_POST,
    body: JSON.stringify({ email }),
  })
}
