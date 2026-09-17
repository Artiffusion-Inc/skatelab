import { render, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { AuthProvider } from "@/components/auth-provider"
import { ConsentProvider } from "@/components/consent-provider"
import * as auth from "@/lib/auth"

vi.mock("@/lib/auth", () => ({ fetchMe: vi.fn().mockResolvedValue(null) }))
afterEach(() => {
  // biome-ignore lint/suspicious/noDocumentCookie: reproduce the existing session sentinel
  document.cookie = "sb_auth=; max-age=0; path=/"
})
it("does not fetch an authenticated account on public pages even with a stale session sentinel", async () => {
  window.history.replaceState({}, "", "/equipment")
  // biome-ignore lint/suspicious/noDocumentCookie: reproduce the existing session sentinel
  document.cookie = "sb_auth=1; path=/"
  render(
    <ConsentProvider>
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <p>Public content</p>
        </AuthProvider>
      </QueryClientProvider>
    </ConsentProvider>,
  )
  await waitFor(() => expect(auth.fetchMe).not.toHaveBeenCalled())
  window.history.replaceState({}, "", "/")
})
