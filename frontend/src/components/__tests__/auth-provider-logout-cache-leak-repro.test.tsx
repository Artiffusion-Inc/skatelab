import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { AuthProvider, useAuth } from "@/components/auth-provider"

// RED repro — logout() clears the sb_auth cookie + nulls user state but NEVER
// calls queryClient.clear() / removeQueries / invalidateQueries. The QueryClient
// is a root singleton (providers.tsx) that lives for the app lifetime. After
// logout the in-memory cache still holds the previous user's ["sessions"],
// ["connections"], ["diagnostics"], ["prs"] query data. On a shared device
// (coach tablet — the exact ABCD-segment in business docs), the NEXT user
// briefly sees the previous user's data for up to staleTime (30s) before a
// background refetch replaces it. This is the frontend analog of the mobile
// #314-#318 Ktor-auth-cache-leak class.

// Mock auth module so logout resolves without network, and fetchMe on mount
// does not blow up. We only care about cache behaviour, not network.
vi.mock("@/lib/auth", () => ({
  logout: vi.fn(() => Promise.resolve()),
  fetchMe: vi.fn(() =>
    Promise.resolve({
      id: "user-1",
      email: "user1@example.com",
      display_name: "User One",
      avatar_url: null,
      bio: null,
      height_cm: null,
      weight_kg: null,
      language: "ru",
      timezone: "Europe/Moscow",
      theme: "system",
      onboarding_role: null,
      is_active: true,
      is_verified: true,
      created_at: new Date().toISOString(),
    }),
  ),
  login: vi.fn(() => Promise.resolve()),
  register: vi.fn(() => Promise.resolve()),
  clearTokens: vi.fn(),
}))

// Mock env so the devMockAuth path is not taken (we want the cookie path).
vi.mock("@/lib/env", () => ({
  devMockAuth: false,
  isDevelopment: false,
}))

// Mock posthog no-ops.
vi.mock("@/lib/posthog", () => ({
  identifyUser: vi.fn(),
  resetIdentity: vi.fn(),
}))

// Consent provider is required by AuthProvider. Minimal stub.
vi.mock("@/components/consent-provider", () => ({
  useConsent: () => ({ hasConsented: () => false }),
}))

function makeQueryClient() {
  // Use a non-zero gcTime so seeded cache entries are NOT immediately GC'd
  // when they have no observers — this mirrors the production singleton
  // (providers.tsx uses gcTime: 5*60_000, staleTime: 30_000), where cache
  // entries persist across logout precisely because logout never clears them.
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 5 * 60_000, staleTime: 30_000 } },
  })
}

function wrap(queryClient: QueryClient, children: ReactNode) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )
}

function LogoutButton() {
  const { logout } = useAuth()
  return (
    <button type="button" data-testid="logout" onClick={() => void logout()}>
      logout
    </button>
  )
}

describe("auth-provider logout cache leak (RED repro)", () => {
  let originalCookie: string
  beforeEach(() => {
    originalCookie = document.cookie
    // Simulate an authenticated session so the mount effect takes the
    // fetchMe path rather than the early return.
    // biome-ignore lint/suspicious/noDocumentCookie: intentional test cookie setup
    document.cookie = "sb_auth=1; path=/"
  })
  afterEach(() => {
    // biome-ignore lint/suspicious/noDocumentCookie: intentional test cookie cleanup
    document.cookie = originalCookie
    vi.clearAllMocks()
  })

  it("sessions + prs cache survives logout (previous user data leaks to next user)", async () => {
    const queryClient = makeQueryClient()

    // Seed the cache with the PREVIOUS user's data, as if they had been
    // browsing sessions / PRs before logging out. These are the exact queryKey
    // shapes used by lib/api/sessions.ts and lib/api/metrics.ts.
    const previousSessions = {
      sessions: [{ id: "old-user-session", display_name: "Previous User" }],
      total: 1,
    }
    const previousPrs = [{ element_type: "flip", best_score: 9.9 }]
    queryClient.setQueryData(["sessions", undefined, undefined], previousSessions)
    queryClient.setQueryData(["prs", undefined, undefined], previousPrs)

    render(wrap(queryClient, <LogoutButton />))

    // Wait for the mount effect (fetchMe) to settle so logout is callable.
    await screen.findByTestId("logout")

    // Fire logout.
    await act(async () => {
      screen.getByTestId("logout").click()
    })

    // Contract: after logout, the React Query cache MUST be cleared so the
    // next user on a shared device cannot see the previous user's data.
    // RED: the cache is NOT cleared by logout(), so the previous user's data
    // survives and leaks to the next user for up to staleTime (30s).
    expect(queryClient.getQueryData(["sessions", undefined, undefined])).toBeUndefined()
    expect(queryClient.getQueryData(["prs", undefined, undefined])).toBeUndefined()
  })
})
