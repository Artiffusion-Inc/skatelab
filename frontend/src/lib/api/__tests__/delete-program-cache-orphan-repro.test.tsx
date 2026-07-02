// RED repro — useDeleteProgram orphans ["program", id] detail cache (#456 mirror, LATENT).
//
// choreography.ts:284-313 useDeleteProgram onSettled only invalidates the
// ["programs"] LIST, never removeQueries(["program", id]) the detail cache.
// The detail query ["program", id] (choreography.ts:249-255) is used by the
// programs/[id] page. After delete, ["program", id] survives gcTime →
// browser-back serves the deleted program. Mirror of #456 (useDeleteSession
// missing removeQueries — FIXED); useDeleteProgram missed the same fix.
//
// LATENT: useDeleteProgram has 0 UI callers today (no delete-program button
// wired in the frontend; backend DELETE /choreography/programs/{id} exists).
// The exported hook is broken but not triggerable in production UI yet.
//
// Mandate: RED test only. No production code edits, no fix-PR.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"

// zod v4 gotcha: choreography.ts uses `import { z } from "zod"` (named import)
// which fails under vitest/oxc transform. Remap named + default both resolve.
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

// A complete ChoreographyProgram object that satisfies ChoreographyProgramSchema.
const completedProgram = {
  id: "p1",
  user_id: "u-1",
  music_analysis_id: null,
  title: "Test Program",
  discipline: "mens_singles",
  segment: "free_skate",
  season: "2026",
  layout: { elements: [] },
  total_tes: 0,
  estimated_goe: null,
  estimated_pcs: null,
  estimated_total: null,
  is_valid: true,
  validation_errors: null,
  validation_warnings: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
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

  // GET /v1/choreography/programs/p1 -> 200 program
  if (method === "GET" && path === "/v1/choreography/programs/p1") {
    return jsonResponse(completedProgram)
  }
  // DELETE /v1/choreography/programs/p1 -> 204
  if (method === "DELETE" && path === "/v1/choreography/programs/p1") {
    return emptyResponse(204)
  }
  // auth/refresh -> 204 (guard, never triggered here)
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

import { useProgram, useDeleteProgram } from "../choreography"

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
// useDeleteProgram orphans ["program", id] detail cache (#456 mirror)
// ===========================================================================
describe("useDeleteProgram orphans detail cache (#456 mirror, latent)", () => {
  it("deleting a program leaves stale ['program', id] data in the cache", async () => {
    // Mirror production: gcTime 5min so the detail cache survives between
    // unmount/remount (the back-button within 5min scenario).
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 5 * 60_000 } },
    })

    // 1. Load the detail page for p1 — populates ["program","p1"].
    const programHook = renderHook(() => useProgram("p1"), {
      wrapper: makeWrapper(qc),
    })
    await waitFor(() => {
      expect(programHook.result.current.data?.id).toBe("p1")
    })
    // Sanity: the cache now holds the program.
    expect(qc.getQueryData(["program", "p1"])).toMatchObject({
      id: "p1",
      title: "Test Program",
    })

    // Production: the user deletes from the list (or navigates away from the
    // detail page first). Unmount the detail hook so the cache entry has no
    // active subscriber that would re-fetch and repopulate it after the
    // removeQueries. (With an active subscriber, React Query refetches on
    // re-mount regardless of the cache state — the orphan test is about the
    // unobserved cache surviving gcTime.)
    programHook.unmount()

    // 2. User deletes the program.
    const deleteHook = renderHook(() => useDeleteProgram(), {
      wrapper: makeWrapper(qc),
    })
    await act(async () => {
      deleteHook.result.current.mutate("p1")
    })
    await waitFor(() => {
      expect(deleteHook.result.current.isSuccess).toBe(true)
    })
    // Confirm the DELETE call actually fired.
    const deleteCalls = fetchMock.mock.calls.filter(([input, init]) => {
      const url = typeof input === "string" ? input : (input as Request).url
      const method = (init?.method ?? "GET").toUpperCase()
      return method === "DELETE" && url.includes("/choreography/programs/p1")
    })
    expect(deleteCalls.length).toBeGreaterThanOrEqual(1)

    // 3. RED ASSERT: the ["program","p1"] cache entry should be gone
    //    (removed or invalidated so it refetches / 404s). Currently it is NOT —
    //    useDeleteProgram onSettled only invalidateQueries(["programs"]) the
    //    LIST, and "programs" (plural list) != "program" (singular detail), so
    //    the prefix match does not touch ["program", id]. The orphaned program
    //    object survives for gcTime (5min), so a back-button remount serves
    //    stale data.
    const orphaned = qc.getQueryData(["program", "p1"])
    // eslint-disable-next-line no-console
    console.log("[useDeleteProgram] orphaned cache entry:", JSON.stringify(orphaned))
    expect(orphaned).toBeUndefined()
  })
})
