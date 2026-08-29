import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import { server } from "@/test/server"
import { useInfiniteSessions } from "../sessions"

const session = {
  id: "session-1",
  user_id: "athlete-1",
  element_type: "axel",
  video_key: null,
  video_url: null,
  processed_video_key: null,
  processed_video_url: null,
  poses_url: null,
  csv_url: null,
  pose_data: null,
  frame_metrics: null,
  status: "completed",
  error_message: null,
  phases: null,
  recommendations: [],
  overall_score: 0.8,
  process_task_id: null,
  imu_left_key: null,
  imu_right_key: null,
  manifest_key: null,
  created_at: "2026-06-01T00:00:00Z",
  processed_at: "2026-06-01T00:10:00Z",
  metrics: [],
  timeline: null,
  segmentation_status: "done",
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  )
}

describe("useInfiniteSessions", () => {
  it("uses the supported coach session filters and follows the backend cursor", async () => {
    const requestedUrls: URL[] = []
    server.use(
      http.get("*/sessions", ({ request }) => {
        const url = new URL(request.url)
        requestedUrls.push(url)
        const hasCursor = url.searchParams.has("cursor")
        return HttpResponse.json({
          sessions: [{ ...session, id: hasCursor ? "session-2" : "session-1" }],
          total: 2,
          next_cursor: hasCursor ? null : "next-page",
          has_more: !hasCursor,
        })
      }),
    )

    const { result } = renderHook(() => useInfiniteSessions("athlete-1", "axel"), { wrapper })
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(1))

    expect(requestedUrls[0].searchParams.get("user_id")).toBe("athlete-1")
    expect(requestedUrls[0].searchParams.get("element_type")).toBe("axel")
    expect(requestedUrls[0].searchParams.get("limit")).toBe("20")
    expect(requestedUrls[0].searchParams.has("status")).toBe(false)
    expect(requestedUrls[0].searchParams.has("date")).toBe(false)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
    expect(requestedUrls[1].searchParams.get("cursor")).toBe("next-page")
    expect(result.current.data?.pages.flatMap(page => page.sessions).map(item => item.id)).toEqual([
      "session-1",
      "session-2",
    ])
  })
})
