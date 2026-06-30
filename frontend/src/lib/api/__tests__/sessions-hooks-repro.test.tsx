// RED repro — two bugs in src/lib/api/sessions.ts:
//   Bug #1: useDeleteSession orphans ["session", id] detail cache.
//   Bug #2: useSession polling refetchInterval misses queued/running/uploading.
//
// Mandate: RED tests only. No production code edits, no fix-PR.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"

// zod v4 gotcha: sessions.ts uses `import { z } from "zod"` (named import) which
// fails under vitest/oxc transform. Remap so named + default both resolve.
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

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

// A complete session object that satisfies SessionSchema.
const completedSession = {
  id: "sess-123",
  user_id: "u-1",
  element_type: "flip",
  video_key: "v/1.mp4",
  video_url: "https://cdn/v/1.mp4",
  processed_video_key: null,
  processed_video_url: null,
  pose_data: null,
  frame_metrics: null,
  status: "completed",
  error_message: null,
  phases: null,
  recommendations: [],
  overall_score: 0.88,
  process_task_id: null,
  imu_left_key: null,
  imu_right_key: null,
  manifest_key: null,
  created_at: "2026-06-01T00:00:00Z",
  processed_at: "2026-06-01T00:10:00Z",
  metrics: [],
  timeline: { segments: [], segmentation_confidence: null, segmentation_status: "done" },
  segmentation_status: "done",
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}
function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

// Route by method + url path.
function routeFetch(req: { method: string; url: string }): Response {
  const { method, url } = req
  const u = new URL(url)
  const path = u.pathname

  // GET /v1/sessions/sess-123 -> 200 completed session
  if (method === "GET" && path === "/v1/sessions/sess-123") {
    return jsonResponse(completedSession)
  }
  // GET /v1/sessions/sess-queued -> 200 queued session (Bug #2)
  if (method === "GET" && path === "/v1/sessions/sess-queued") {
    return jsonResponse({ ...completedSession, id: "sess-queued", status: "queued" })
  }
  // DELETE /v1/sessions/sess-123 -> 204
  if (method === "DELETE" && path === "/v1/sessions/sess-123") {
    return emptyResponse(204)
  }
  // auth/refresh -> 204 (never triggered in these tests, but guard)
  if (method === "POST" && path === "/v1/auth/refresh") {
    return emptyResponse(204)
  }
  return new Response(JSON.stringify({ detail: `unmocked ${method} ${path}` }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  })
}

fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" || input instanceof URL ? input.toString() : (input as Request).url
  const method = (init?.method ?? "GET").toUpperCase()
  return routeFetch({ method, url })
})
globalThis.fetch = fetchMock as unknown as typeof fetch

import { useSession, useDeleteSession } from "../sessions"

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
// Bug #1: useDeleteSession orphans ["session", id] detail cache
// ===========================================================================
describe("Bug #1 — useDeleteSession orphans detail cache", () => {
  it("deleting a session leaves stale ['session', id] data in the cache", async () => {
    // Mirror production: gcTime 5min so the detail cache survives between
    // unmount/remount (the back-button within 5min scenario).
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 5 * 60_000 } },
    })

    // 1. Load the detail page for sess-123 — populates ["session","sess-123"].
    const sessionHook = renderHook(() => useSession("sess-123"), {
      wrapper: makeWrapper(qc),
    })
    await waitFor(() => {
      expect(sessionHook.result.current.data?.id).toBe("sess-123")
    })
    // Sanity: the cache now holds the completed session.
    expect(qc.getQueryData(["session", "sess-123"])).toMatchObject({
      id: "sess-123",
      status: "completed",
    })

    // 2. User deletes the session.
    const deleteHook = renderHook(() => useDeleteSession(), {
      wrapper: makeWrapper(qc),
    })
    await act(async () => {
      deleteHook.result.current.mutate("sess-123")
    })
    await waitFor(() => {
      expect(deleteHook.result.current.isSuccess).toBe(true)
    })
    // Confirm the DELETE call actually fired.
    const deleteCalls = fetchMock.mock.calls.filter(([input, init]) => {
      const url = typeof input === "string" ? input : (input as Request).url
      const method = (init?.method ?? "GET").toUpperCase()
      return method === "DELETE" && url.includes("/sessions/sess-123")
    })
    expect(deleteCalls.length).toBeGreaterThanOrEqual(1)

    // 3. RED ASSERT: the ["session","sess-123"] cache entry should be gone
    //    (removed or invalidated so it refetches / 404s). Currently it is NOT —
    //    useDeleteSession only invalidates the ["sessions"] LIST, and because
    //    "session" (singular) != "sessions" (plural), the prefix match does
    //    not touch ["session", id]. The orphaned completed-session object
    //    survives for gcTime (5min), so a back-button remount serves stale data.
    const orphaned = qc.getQueryData(["session", "sess-123"])
    // Capture the actual orphaned value for the receipt.
    // eslint-disable-next-line no-console
    console.log("[Bug#1] orphaned cache entry:", JSON.stringify(orphaned))
    expect(orphaned).toBeUndefined()
  })
})

// ===========================================================================
// Bug #2: useSession polling refetchInterval misses queued/running/uploading
// ===========================================================================
describe("Bug #2 — useSession polling misses queued", () => {
  it("a 'queued' session (in the UI POLLING_STATUSES set) should be polled, but refetchInterval returns false", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    const { result } = renderHook(() => useSession("sess-queued"), {
      wrapper: makeWrapper(qc),
    })

    // Wait for the initial fetch to resolve with status:"queued".
    await waitFor(() => {
      expect(result.current.data?.status).toBe("queued")
    })
    const callsAfterInitial = fetchMock.mock.calls.length

    // The contract: queued is in the session-detail page's POLLING_STATUSES
    // set, so the UI shows a "processing" banner and expects live progress.
    // The hook's refetchInterval (sessions.ts:113-118) only fires for
    // status==="processing" + segmentation_status==="pending" — NOT queued —
    // so it returns false and never polls. Advance past the 5000ms poll window.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000)
    })
    const callsAfterPollWindow = fetchMock.mock.calls.length

    // eslint-disable-next-line no-console
    console.log(
      `[Bug#2] fetch calls: initial=${callsAfterInitial}, after 6s=${callsAfterPollWindow}`,
    )

    // RED ASSERT: a queued (in-progress) session SHOULD poll, so the call
    // count must have grown. Currently it does not — the predicate returns
    // false for "queued", so callsAfter === callsBefore.
    expect(callsAfterPollWindow).toBeGreaterThan(callsAfterInitial)
  })
})