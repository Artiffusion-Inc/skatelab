import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import { server } from "@/test/server"

import ConnectionsPage from "@/app/(app)/connections/page"

const invitedConnection = {
  id: "connection-1",
  from_user_id: "coach-1",
  to_user_id: "athlete-1",
  connection_type: "coaching",
  status: "invited",
  initiated_by: "coach-1",
  created_at: "2026-06-01T00:00:00Z",
  ended_at: null,
  from_user_name: "Coach",
  to_user_name: "Athlete",
}

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
      }
    >
      <ConnectionsPage />
    </QueryClientProvider>,
  )
}

describe("connections invite flow", () => {
  it("keeps the invite form available when there are no connections", async () => {
    let inviteBody: unknown
    server.use(
      http.get("*/connections", () => HttpResponse.json({ connections: [], total: 0 })),
      http.get("*/connections/pending", () => HttpResponse.json({ connections: [], total: 0 })),
      http.post("*/connections/invite", async ({ request }) => {
        inviteBody = await request.json()
        return HttpResponse.json(invitedConnection, { status: 201 })
      }),
    )

    renderPage()

    const email = await screen.findByLabelText(/email/i)
    await userEvent.type(email, "athlete@example.com")
    await userEvent.click(screen.getByRole("button", { name: /пригласить|invite/i }))

    await waitFor(() => {
      expect(inviteBody).toEqual({
        to_user_email: "athlete@example.com",
        connection_type: "coaching",
      })
    })
  })
})
