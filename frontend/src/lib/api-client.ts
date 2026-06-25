/**
 * Shared API infrastructure: base URL, cookie-based auth, typed fetch helper,
 * silent refresh with mutex on 401.
 *
 * Auth tokens are now set as httpOnly cookies by the backend.
 * The frontend only manages the `sb_auth` sentinel cookie for SSR gating.
 */

import * as z from "zod"

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.skatelab.ru/v1"

// ---------------------------------------------------------------------------
// Token storage (stubs — cookies set by backend, kept for rollback compat)
// ---------------------------------------------------------------------------

/** @deprecated Cookies are set by the backend. Returns null. */
export function getAccessToken(): string | null {
  return null
}

/** @deprecated Cookies are set by the backend. Returns null. */
export function getRefreshToken(): string | null {
  return null
}

/** @deprecated No-op: tokens are now set via httpOnly cookies by the backend. Stub kept for rollback compat. */
export function setTokens(_access: string, _refresh: string): void {
  // No-op: backend sets httpOnly cookies via Set-Cookie headers.
  // Keep sb_auth sentinel for SSR gating
  // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
  document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax; Domain=skatelab.ru"
}

export function clearTokens(): void {
  // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
  document.cookie = "sb_auth=; path=/; max-age=0; Domain=skatelab.ru"
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
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    })
    if (!res.ok) return false

    // Backend sets new httpOnly cookies via Set-Cookie headers automatically.
    // Refresh the sb_auth sentinel so SSR gating stays in sync.
    // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
    document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax; Domain=skatelab.ru"
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
      credentials: "include",
      headers,
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
          credentials: "include",
          headers,
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
    credentials: "include",
    headers: init?.headers,
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
        credentials: "include",
        headers: init?.headers,
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

const VoidSchema = z.any().transform(() => undefined)

export async function apiDelete(path: string): Promise<void> {
  return apiFetch(path, VoidSchema, { method: "DELETE" })
}
