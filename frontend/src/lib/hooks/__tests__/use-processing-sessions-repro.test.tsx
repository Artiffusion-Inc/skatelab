// RED repro — two bugs in src/lib/hooks/use-processing-sessions.ts (#457 sibling, LATENT):
//   Bug A: refetchInterval: 30_000 static constant — over-poll never stops, even when
//          processingCount===0 / all-terminal. Fixed sibling useSession (sessions.ts:127-138)
//          uses refetchInterval: query => predicate returning false on terminal — this
//          hook has no such guard.
//   Bug B: hook calls apiFetch("/sessions?status=processing") but backend list_sessions
//          accepts only user_id/element_type/limit/cursor — NO status param; Litestar
//          silently drops unknown query params; hook does data?.sessions.length with NO
//          client-side status filter → processingCount = ALL non-deleted sessions
//          (done+failed+queued+everything), hasProcessing true for any user with ≥1
//          session → permanently-stuck "processing" badge.
//
// Mandate: RED tests only. No production code edits, no fix-PR.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"

// zod v4 gotcha: hook uses `import { z } from "zod"` (named import) which fails under
// vitest/oxc transform. Remap so named + default both resolve.
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

// Mock useAuth so the hook's `enabled: !!user` is true without a provider tree.
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: { id: "u-1" } }),
}))

// ---- mock fetch (routed by method + url) ---------------------------------
const fetchMock = vi.fn()
let cookieJar = ""
Object.defineProperty(globalThis.document, "cookie", {
  get: () => cookieJar,
  set: (v: string) => {
    cookieJar = v
  },
  configurable: true,
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

// All-terminal response: NO session is actually "processing". Backend silently drops
// the ?status=processing param and returns ALL non-deleted sessions (done/failed/
// completed). The hook counts every entry → processingCount = 3, hasProcessing = true.
const allTerminalSessions = {
  sessions: [
    { id: "1", status: "done" },
    { id: "2", status: "failed" },
    { id: "3", status: "completed" },
  ],
  total: 3,
}

function routeFetch(req: { method: string; url: string }): Response {
  const { method, url } = req
  const u = new URL(url)
  const path = u.pathname

  // GET /v1/sessions (with any query string incl. ?status=processing) -> all-terminal list.
  // Backend ignores the unknown status param and returns all non-deleted sessions.
  if (method === "GET" && path === "/v1/sessions") {
    return jsonResponse(allTerminalSessions)
  }
  // auth/refresh -> 204 (guard, never triggered here)
  if (method === "POST" && path === "/v1/auth/refresh") {
    return new Response(null, { status: 204 })
  }
  return new Response(JSON.stringify({ detail: `unmocked ${method} ${path}` }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  })
}

fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url =
    typeof input === "string" || input instanceof URL ? input.toString() : (input as Request).url
  const method = (init?.method ?? "GET").toUpperCase()
  return routeFetch({ method, url })
})
globalThis.fetch = fetchMock as unknown as typeof fetch

import { useProcessingSessions } from "../use-processing-sessions"

function makeWrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

beforeEach(() => {
  fetchMock.mockClear()
  cookieJar = ""
})
afterEach(() => {
  vi.useRealTimers()
})

// ===========================================================================
// Bug B: status filter silently dropped → processingCount = ALL non-deleted
// ===========================================================================
describe("Bug B — ?status=processing silently dropped, no client-side filter", () => {
  it("counts ALL non-deleted sessions as 'processing' (no session is actually processing)", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    const { result } = renderHook(() => useProcessingSessions(), {
      wrapper: makeWrapper(qc),
    })

    // Wait for the initial fetch to resolve.
    await waitFor(() => {
      expect(result.current.processingCount).toBe(0)
    })

    // eslint-disable-next-line no-console
    console.log(
      `[Bug B] hasProcessing=${result.current.hasProcessing}, processingCount=${result.current.processingCount}`,
    )

    // Contract: none of the 3 sessions is actually processing (done/failed/completed),
    // so the hook should report hasProcessing=false, processingCount=0.
    // RED now: hasProcessing=true, processingCount=3 (status param dropped + no filter).
    expect(result.current.hasProcessing).toBe(false)
    expect(result.current.processingCount).toBe(0)
  })
})

// ===========================================================================
// Bug A: refetchInterval static 30_000 — over-poll never stops on all-terminal
// ===========================================================================
describe("Bug A — over-poll never stops (static refetchInterval, no terminal guard)", () => {
  it("refetchInterval must be a predicate function that stops polling on all-terminal; static 30_000 never stops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    const { result } = renderHook(() => useProcessingSessions(), {
      wrapper: makeWrapper(qc),
    })

    // Wait for the initial fetch to resolve with all-terminal data.
    await waitFor(() => {
      expect(result.current.processingCount).toBe(0)
    })
    const callsAfterInitial = fetchMock.mock.calls.length

    // Advance 60s = 2× the 30s refetchInterval. The fixed sibling (useSession)
    // stops polling once data is terminal (predicate returns false). This hook
    // uses a static 30_000 so it MUST fire again despite all-terminal data.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    const callsAfter60s = fetchMock.mock.calls.length

    // eslint-disable-next-line no-console
    console.log(`[Bug A] fetch calls: initial=${callsAfterInitial}, after 60s=${callsAfter60s}`)

    // Contract: when no sessions are actually processing, polling should STOP —
    // the call count must NOT grow. RED now: static 30_000 keeps firing, so
    // callsAfter60s > callsAfterInitial (over-poll on all-terminal data).
    expect(callsAfter60s).toBe(callsAfterInitial)
  })
})
