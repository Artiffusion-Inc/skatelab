import { describe, expect, it, vi, beforeEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"

// Keep this test compatible with the named zod import used by the API module.
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

const fetchMock = vi.fn()
globalThis.fetch = fetchMock as unknown as typeof fetch

import { useSession } from "../sessions"
import { useSessionScores } from "../analyzer"

const incompleteSessionResult = {
  id: "session-result-1",
  user_id: "user-1",
  element_type: null,
  video_url: null,
  processed_video_url: null,
  status: "done",
  error_message: null,
  phases: { takeoff: 0, peak: 45, landing: null },
  recommendations: null,
  overall_score: null,
  created_at: "2026-08-30T10:00:00Z",
  processed_at: null,
  metrics: [],
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe("session result API contract", () => {
  beforeEach(() => fetchMock.mockReset())

  it("parses nullable fields, missing provenance, and integer phase markers", async () => {
    fetchMock.mockResolvedValue(jsonResponse(incompleteSessionResult))

    const { result } = renderHook(() => useSession(incompleteSessionResult.id), {
      wrapper: makeWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toMatchObject({
      id: incompleteSessionResult.id,
      element_type: null,
      phases: {
        takeoff: { frame: 0 },
        peak: { frame: 45 },
        landing: null,
      },
      recommendations: null,
      overall_score: null,
      metrics: [],
      segmentation_status: "pending",
    })
    expect(result.current.data?.imu_left_key).toBeNull()
    expect(result.current.data?.imu_right_key).toBeNull()
    expect(result.current.data?.manifest_key).toBeNull()
  })

  it("uses a stable default when the score response omits data_quality", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "score-1",
        session_id: "session-result-1",
        subscores: [
          {
            name: "technique",
            label_ru: "Техника",
            value: 8,
            confidence: 0.9,
            contributing_metrics: ["airtime"],
          },
        ],
        overall: 8,
        skeleton_reliability: "reliable",
        created_at: "2026-08-30T10:00:00Z",
        updated_at: "2026-08-30T10:00:00Z",
      }),
    )

    const { result } = renderHook(() => useSessionScores("session-result-1"), {
      wrapper: makeWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toMatchObject({ overall: 8, data_quality: "good" })
  })
})
