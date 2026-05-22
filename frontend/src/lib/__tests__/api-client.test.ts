import { assert, describe, expect, it, vi, beforeEach } from "vitest"
import { z } from "zod"

// Mock window.location.href redirect
const mockRedirect = vi.fn()
const originalLocation = window.location
Object.defineProperty(globalThis.window, "location", {
  value: { ...originalLocation, href: "" },
  writable: true,
  configurable: true,
})
// Override href setter to track redirects
Object.defineProperty(globalThis.window.location, "href", {
  set: (v: string) => {
    mockRedirect(v)
  },
  get: () => "",
  configurable: true,
})

// Mock document.cookie
let cookieJar = ""
Object.defineProperty(globalThis.document, "cookie", {
  get: () => cookieJar,
  set: (v: string) => {
    cookieJar = v
  },
  configurable: true,
})

// Mock navigator.onLine
Object.defineProperty(globalThis.navigator, "onLine", {
  get: () => true,
  configurable: true,
})

// Mock fetch
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

import {
  apiFetch,
  apiPost,
  apiPatch,
  apiDelete,
  authFetch,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  ApiError,
} from "../api-client"

const TestSchema = z.object({ id: z.string(), name: z.string() })

// Helper to create mock Response objects
function mockResponse(opts: { ok?: boolean; status?: number; json?: () => Promise<unknown> }) {
  const ok = opts.ok ?? (opts.status !== undefined ? opts.status >= 200 && opts.status < 300 : true)
  const status = opts.status ?? 200
  return {
    ok,
    status,
    json: opts.json ?? (() => Promise.resolve({})),
  }
}

describe(apiFetch, () => {
  beforeEach(() => {
    mockFetch.mockReset()
    mockRedirect.mockReset()
    cookieJar = ""
  })

  it("throws ApiError when offline", () => {
    const originalOnline = navigator.onLine
    Object.defineProperty(globalThis.navigator, "onLine", { value: false, configurable: true })
    try {
      return expect(apiFetch("/test", TestSchema)).rejects.toThrow(ApiError)
    } finally {
      Object.defineProperty(globalThis.navigator, "onLine", {
        value: originalOnline,
        configurable: true,
      })
    }
  })

  it("sends request with credentials: include (cookie auth)", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ json: () => Promise.resolve({ id: "1", name: "test" }) }),
    )

    const result = await apiFetch("/users/me", TestSchema)
    expect(result).toEqual({ id: "1", name: "test" })
    expect(mockFetch.mock.calls[0][1]?.credentials).toBe("include")
  })

  it("returns undefined for 204 No Content", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ status: 204 }))

    const result = await apiFetch("/delete-me", z.unknown(), { method: "DELETE" })
    expect(result).toBeUndefined()
  })

  it("throws ApiError with detail from response body", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Not found" }),
      }),
    )

    await expect(apiFetch("/missing", TestSchema)).rejects.toSatisfy(err => {
      assert(err instanceof ApiError)
      expect(err.message).toBe("Not found")
      expect(err.status).toBe(404)
      return true
    })
  })

  it("falls back to HTTP status in detail when body parse fails", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("invalid json")),
      }),
    )

    await expect(apiFetch("/broken", TestSchema)).rejects.toSatisfy(err => {
      assert(err instanceof ApiError)
      expect(err.status).toBe(500)
      return true
    })
  })

  it("wraps network errors in ApiError", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"))

    await expect(apiFetch("/network-fail", TestSchema)).rejects.toSatisfy(err => {
      assert(err instanceof ApiError)
      expect(err.message).toBe("Failed to fetch")
      expect(err.status).toBe(0)
      return true
    })
  })
})

describe("silent refresh on 401", () => {
  beforeEach(() => {
    mockFetch.mockReset()
    mockRedirect.mockReset()
    cookieJar = ""
  })

  it("refreshes on 401 and retries request", async () => {
    // First call: 401
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: "Unauthorized" }),
      }),
    )
    // Refresh call: success (backend sets new cookies)
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        json: () => Promise.resolve({ access_token: "new-access", refresh_token: "new-refresh" }),
      }),
    )
    // Retry call: success
    mockFetch.mockResolvedValueOnce(
      mockResponse({ json: () => Promise.resolve({ id: "1", name: "refreshed" }) }),
    )

    const result = await apiFetch("/protected", TestSchema)
    expect(result).toEqual({ id: "1", name: "refreshed" })
    expect(mockFetch).toHaveBeenCalledTimes(3)
    // Verify refresh call uses credentials: include
    expect(mockFetch.mock.calls[1][1]?.credentials).toBe("include")
  })

  it("throws ApiError(401) when refresh fails", async () => {
    // First call: 401
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: "Unauthorized" }),
      }),
    )
    // Refresh call: fails
    mockFetch.mockResolvedValueOnce(mockResponse({ ok: false, status: 401 }))

    await expect(apiFetch("/protected", TestSchema)).rejects.toSatisfy(err => {
      assert(err instanceof ApiError)
      expect(err.status).toBe(401)
      return true
    })
  })
})

describe(apiPost, () => {
  beforeEach(() => {
    mockFetch.mockReset()
    cookieJar = ""
  })

  it("sends POST request with JSON body", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ json: () => Promise.resolve({ id: "1", name: "created" }) }),
    )

    await apiPost("/items", TestSchema, { name: "new" })
    const init = mockFetch.mock.calls[0][1]
    expect(init?.method).toBe("POST")
    expect(JSON.parse(init?.body as string)).toEqual({ name: "new" })
  })
})

describe(apiPatch, () => {
  beforeEach(() => {
    mockFetch.mockReset()
    cookieJar = ""
  })

  it("sends PATCH request with JSON body", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ json: () => Promise.resolve({ id: "1", name: "updated" }) }),
    )

    await apiPatch("/items/1", TestSchema, { name: "patched" })
    const init = mockFetch.mock.calls[0][1]
    expect(init?.method).toBe("PATCH")
  })
})

describe(apiDelete, () => {
  beforeEach(() => {
    mockFetch.mockReset()
    cookieJar = ""
  })

  it("sends DELETE request and returns void on 204", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ status: 204 }))

    const result = await apiDelete("/items/1")
    expect(result).toBeUndefined()
    const init = mockFetch.mock.calls[0][1]
    expect(init?.method).toBe("DELETE")
  })
})

describe(authFetch, () => {
  beforeEach(() => {
    mockFetch.mockReset()
    mockRedirect.mockReset()
    cookieJar = ""
  })

  it("returns response on success with credentials: include", async () => {
    const mockRes = mockResponse({ status: 200 })
    mockFetch.mockResolvedValueOnce(mockRes)

    const result = await authFetch("/data")
    expect(result).toBe(mockRes)
    expect(mockFetch.mock.calls[0][1]?.credentials).toBe("include")
  })

  it("refreshes on 401 and retries", async () => {
    // First call: 401
    mockFetch.mockResolvedValueOnce(mockResponse({ ok: false, status: 401 }))
    // Refresh
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        json: () => Promise.resolve({ access_token: "new", refresh_token: "new-r" }),
      }),
    )
    // Retry
    mockFetch.mockResolvedValueOnce(mockResponse({ status: 200 }))

    await authFetch("/protected")
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })
})

describe("cookie-based auth", () => {
  beforeEach(() => {
    cookieJar = ""
  })

  it("getAccessToken returns null (deprecated stub)", () => {
    expect(getAccessToken()).toBeNull()
  })

  it("getRefreshToken returns null (deprecated stub)", () => {
    expect(getRefreshToken()).toBeNull()
  })

  it("clearTokens removes sb_auth cookie", () => {
    cookieJar = "sb_auth=1"
    clearTokens()
    // clearTokens sets document.cookie to delete sb_auth
    expect(cookieJar).toContain("sb_auth=")
    expect(cookieJar).toContain("max-age=0")
  })
})
