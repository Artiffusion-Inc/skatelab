import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import { server } from "@/test/server"
import { useCreateComment } from "../comments"

describe("useCreateComment", () => {
  it("posts the typed comment response and invalidates session caches", async () => {
    let requestBody: unknown
    server.use(
      http.post("*/sessions/session-1/comments", async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.json({
          id: "comment-1",
          session_id: "session-1",
          coach_id: "coach-1",
          content: "Keep the landing knee soft",
          created_at: "2026-08-30T10:05:00Z",
        })
      }),
    )

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(["sessions"], { sessions: [] })
    queryClient.setQueryData(["session", "session-1"], { id: "session-1" })

    const hook = renderHook(() => useCreateComment(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    })

    await act(async () => {
      hook.result.current.mutate({ sessionId: "session-1", content: "Keep the landing knee soft" })
    })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))

    expect(requestBody).toEqual({ content: "Keep the landing knee soft" })
    expect(hook.result.current.data).toEqual({
      id: "comment-1",
      session_id: "session-1",
      coach_id: "coach-1",
      content: "Keep the landing knee soft",
      created_at: "2026-08-30T10:05:00Z",
    })
    expect(queryClient.getQueryState(["sessions"])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(["session", "session-1"])?.isInvalidated).toBe(true)
  })
})
