// RED repro — accept/end connection buttons fire mutateAsync with no error
// handling → silent failure + unhandled promise rejection on API error.
//
// connections/page.tsx:
//   :112  onClick={() => acceptConn.mutateAsync(r.id)}   // no .catch / try-catch
//   :133  onClick={() => endConn.mutateAsync(r.id)}      // same
//
// connections.ts:43-57: useAcceptConnection / useEndConnection have onSuccess
// ONLY, NO onError.
//
// Compare handleInvite (connections/page.tsx:33-41) which correctly wraps
// invite.mutateAsync in try/catch + toast.error — the correct pattern, in
// the SAME file. So accept/end are inconsistent with invite within the same
// page: on API failure (500/network/already-ended race) the user clicks
// Accept/End, nothing visibly happens, no toast, unhandled rejection in
// console.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { server } from "@/test/server"
import { render, screen, waitFor } from "@/test/test-utils"

// zod v4 gotcha: connections.ts uses `import { z } from "zod"` (named import)
// which fails under vitest/oxc transform. Remap so named + default both
// resolve. (Mirrors sessions-hooks-repro.test.tsx pattern.)
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

// Capture toast.error calls — the contract is that accept failure MUST show
// a toast.error (matching handleInvite's behavior). RED now: no toast.error
// is called because accept's onClick has no try/catch.
const toastError = vi.fn()
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

// A pending connection row (matches ConnectionSchema). The accept button
// is rendered for pending connections (page.tsx:101-120).
const pendingConn = {
  id: "conn-pending-1",
  from_user_id: "u-from",
  to_user_id: "u-me",
  connection_type: "coaching",
  status: "invited",
  initiated_by: "u-from",
  created_at: "2026-06-01T00:00:00Z",
  ended_at: null,
  from_user_name: "Алиса",
  to_user_name: null,
}

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

// Import the page AFTER mocks are registered (vi.mock is hoisted, but the
// import must still come after the zod mock is set up — placing it here
// mirrors the sessions-hooks-repro pattern).
import ConnectionsPage from "@/app/(app)/connections/page"

beforeEach(() => {
  toastError.mockClear()
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe("accept connection — unhandled rejection on API failure (RED repro)", () => {
  it("shows a toast.error when accept fails (matching handleInvite); RED now: no toast, silent failure", async () => {
    server.use(
      // Existing active connections (empty — so the pending section renders).
      http.get("*/connections", () => HttpResponse.json({ connections: [] })),
      // Pending connection list — contains our pending row.
      http.get("*/connections/pending", () => HttpResponse.json({ connections: [pendingConn] })),
      // Accept endpoint → 500 (server error).
      http.post("*/connections/conn-pending-1/accept", () =>
        HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 }),
      ),
    )

    withProviders(<ConnectionsPage />)

    // Wait for the pending connection to render + the Accept button.
    const acceptBtn = await screen.findByRole("button", { name: /принять|accept/i })
    expect(acceptBtn).toBeTruthy()

    // Click accept → fires acceptConn.mutateAsync(r.id) with no try/catch.
    acceptBtn.click()

    // CONTRACT: on API failure, a toast.error MUST be shown — matching the
    // handleInvite pattern (page.tsx:33-41) which wraps invite.mutateAsync in
    // try/catch + toast.error. RED now: no toast.error is called because
    // accept's onClick (page.tsx:112) has no error handling and the hook
    // (connections.ts:43-49) has onSuccess ONLY, no onError.
    await waitFor(
      () => {
        expect(toastError).toHaveBeenCalled()
      },
      { timeout: 3000 },
    )
  })
})
