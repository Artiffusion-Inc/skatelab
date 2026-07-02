// RED repro — useBulkDeleteSessions orphans ["session", id] detail cache.
//
// BUG (LOW-MEDIUM — cache orphan / invalidation-gap, #456 mirror):
//   frontend/src/lib/api/sessions.ts:188-193 `useBulkDeleteSessions.onSuccess`
//   only does `qc.invalidateQueries({ queryKey: ["sessions"] })` (the LIST
//   key, plural). It does NOT `qc.removeQueries({ queryKey: ["session", id] })`
//   for each deleted id (singular) — unlike `useDeleteSession` (:172-185)
//   which the #456 fix taught to `removeQueries(["session", id])`.
//
//   "session" (singular) != "sessions" (plural), so the list invalidation's
//   prefix match does NOT touch the detail cache. After a bulk delete, the
//   completed-session object for each deleted id survives in cache for
//   gcTime (5min default) → browser-back / direct nav to /sessions/{id}
//   serves the stale deleted session instead of a 404 / "not found".
//
//   This is the exact #456 bug class, one consumer over: single-delete was
//   fixed (#456), bulk-delete was missed.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"

// zod v4 gotcha: sessions.ts uses `import { z } from "zod"` (named import)
// which fails under vitest/oxc transform. Remap so named + default both
// resolve. (Mirrors sessions-hooks-repro.test.tsx pattern.)
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
  id: "s1",
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

function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

function routeFetch(req: { method: string; url: string }): Response {
  const { method, url } = req
  const u = new URL(url)
  const path = u.pathname

  // DELETE /v1/sessions/bulk?ids=s1[,s2...] -> 204
  if (method === "DELETE" && path === "/v1/sessions/bulk") {
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
  const url =
    typeof input === "string" || input instanceof URL ? input.toString() : (input as Request).url
  const method = (init?.method ?? "GET").toUpperCase()
  return routeFetch({ method, url })
})
globalThis.fetch = fetchMock as unknown as typeof fetch

import { useBulkDeleteSessions } from "../sessions"

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

describe("useBulkDeleteSessions orphans ['session', id] detail cache (#456 mirror, RED repro)", () => {
  it("bulk-deleting sessions leaves stale ['session', id] data in the cache for each deleted id", async () => {
    // Mirror production: gcTime 5min so the detail cache survives between
    // unmount/remount (the back-button within 5min scenario).
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 5 * 60_000 } },
    })

    // 1. Seed the detail cache for ["session","s1"] directly (simulates a
    //    user having already visited /sessions/s1 — the completed-session
    //    object is now cached).
    qc.setQueryData(["session", "s1"], completedSession)
    // Sanity: the cache now holds the completed session.
    expect(qc.getQueryData(["session", "s1"])).toMatchObject({
      id: "s1",
      status: "completed",
    })

    // 2. User bulk-deletes session s1.
    const bulkHook = renderHook(() => useBulkDeleteSessions(), {
      wrapper: makeWrapper(qc),
    })
    await act(async () => {
      bulkHook.result.current.mutate(["s1"])
    })
    await waitFor(() => {
      expect(bulkHook.result.current.isSuccess).toBe(true)
    })
    // Confirm the bulk DELETE call actually fired.
    const deleteCalls = fetchMock.mock.calls.filter(([input, init]) => {
      const url = typeof input === "string" ? input : (input as Request).url
      const method = (init?.method ?? "GET").toUpperCase()
      return method === "DELETE" && url.includes("/sessions/bulk")
    })
    expect(deleteCalls.length).toBeGreaterThanOrEqual(1)

    // 3. RED ASSERT: the ["session","s1"] cache entry should be gone (removed
    //    via removeQueries for each bulk-deleted id, mirroring the #456
    //    single-delete fix). Currently it is NOT — useBulkDeleteSessions only
    //    invalidates the ["sessions"] LIST, and "session" (singular) !=
    //    "sessions" (plural), so the prefix match does not touch ["session",
    //    id]. The orphaned completed-session object survives for gcTime
    //    (5min), so a back-button remount serves stale data.
    const orphaned = qc.getQueryData(["session", "s1"])
    // eslint-disable-next-line no-console
    console.log("[Bug#bulk] orphaned cache entry:", JSON.stringify(orphaned))
    expect(orphaned).toBeUndefined()
  })
})
