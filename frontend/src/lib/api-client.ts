/**
 * Shared API infrastructure: base URL, token storage, typed fetch helper,
 * silent refresh with mutex on 401.
 */

import { z } from "zod"

export const API_BASE = "/api/v1"

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

const TOKEN_KEY = "access_token"
const REFRESH_KEY = "refresh_token"

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
  // biome-ignore lint: sync auth cookie for SSR gating
  document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax"
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  // biome-ignore lint: clear auth cookie on logout
  document.cookie = "sb_auth=; path=/; max-age=0"
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

// ---------------------------------------------------------------------------
// Silent refresh mutex
// ---------------------------------------------------------------------------

let refreshPromise: Promise<boolean> | null = null

async function silentRefresh(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return false

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    if (!res.ok) return false

    const data: { access_token: string; refresh_token: string } = await res.json()
    setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

function handleAuthFailure(): never {
  clearTokens()
  throw new ApiError("Authentication required", 401)
}

// ---------------------------------------------------------------------------
// Typed fetch
// ---------------------------------------------------------------------------

function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiFetch<T>(
  path: string,
  schema: z.ZodSchema<T>,
  init?: RequestInit & { auth?: boolean },
): Promise<T> {
  const { auth = true, headers, ...rest } = init ?? {}

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    throw new ApiError("No internet connection", 0)
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: { ...(auth ? authHeaders() : {}), ...headers },
    })
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "Network error", 0)
  }

  // Silent refresh on 401: mutex ensures only one refresh at a time
  if (res.status === 401 && auth) {
    if (!refreshPromise) {
      refreshPromise = silentRefresh().finally(() => {
        refreshPromise = null
      })
    }
    const refreshed = await refreshPromise
    if (refreshed) {
      try {
        const retryRes = await fetch(`${API_BASE}${path}`, {
          ...rest,
          headers: { ...authHeaders(), ...headers },
        })
        if (retryRes.status === 204) return undefined as T
        if (!retryRes.ok) {
          const body = await retryRes.json().catch(() => ({ detail: `HTTP ${retryRes.status}` }))
          throw new ApiError(body.detail, retryRes.status)
        }
        return schema.parse(await retryRes.json())
      } catch (error) {
        if (error instanceof ApiError) throw error
        throw new ApiError(error instanceof Error ? error.message : "Network error", 0)
      }
    }
    handleAuthFailure()
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new ApiError(body.detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return schema.parse(await res.json())
}

// ---------------------------------------------------------------------------
// Raw auth fetch (for FormData, SSE, etc.)
// ---------------------------------------------------------------------------

export async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  })

  if (res.status === 401) {
    if (!refreshPromise) {
      refreshPromise = silentRefresh().finally(() => {
        refreshPromise = null
      })
    }
    const refreshed = await refreshPromise
    if (refreshed) {
      return fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { ...authHeaders(), ...init?.headers },
      })
    }
    handleAuthFailure()
  }

  return res
}

// ---------------------------------------------------------------------------
// Convenience helpers
// ---------------------------------------------------------------------------

export async function apiPost<T>(path: string, schema: z.ZodSchema<T>, body: unknown): Promise<T> {
  return apiFetch<T>(path, schema, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  })
}

export async function apiPatch<T>(path: string, schema: z.ZodSchema<T>, body: unknown): Promise<T> {
  return apiFetch<T>(path, schema, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  })
}

const VoidSchema = z.unknown().transform(() => undefined)

export async function apiDelete(path: string): Promise<void> {
  return apiFetch(path, VoidSchema, { method: "DELETE" })
}
