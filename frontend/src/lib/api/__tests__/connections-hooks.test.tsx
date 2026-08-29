import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor, act } from "@testing-library/react"
import type { ReactNode } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it, vi } from "vitest"
import { server } from "@/test/server"
import { useAcceptConnection } from "../connections"

const acceptedConnection = {
  id: "connection-1",
  from_user_id: "coach-1",
  to_user_id: "athlete-1",
  connection_type: "coaching",
  status: "active",
  initiated_by: "coach-1",
  created_at: "2026-06-01T00:00:00Z",
  ended_at: null,
  from_user_name: "Coach",
  to_user_name: "Athlete",
}

describe("connection mutations", () => {
  it("invalidates connection and coach session caches after accepting", async () => {
    server.use(
      http.post("*/connections/connection-1/accept", () => HttpResponse.json(acceptedConnection)),
    )
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useAcceptConnection(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync("connection-1")
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["connections"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sessions"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["session"] })
  })
})
