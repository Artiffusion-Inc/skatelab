/**
 * RED repro — logged-in user navigating to /login sees the auth form instead
 * of being redirected to /feed (redirect-gap / stale-closure mount-effect).
 *
 * `LoginPage` (src/app/(auth)/login/page.tsx:23-27):
 *
 *   useMountEffect(() => {
 *     if (isAuthenticated) router.push("/feed")
 *   })
 *
 * `useMountEffect` (src/lib/useMountEffect.ts:9) = `useEffect(callback, [])`
 * — mount-only, empty deps, runs ONCE.
 *
 * At INITIAL mount, `auth-provider.tsx` state is:
 *   - `isLoading = true`      (auth-provider.tsx:29)
 *   - `user = null`           (auth-provider.tsx:28)
 *   - `isAuthenticated = false` (derived: `!!user`, auth-provider.tsx:121)
 *
 * `fetchMe()` is fired in the provider's OWN `useMountEffect` (auth-provider.tsx:
 * 32-68) and resolves asynchronously. So at the moment `LoginPage`'s
 * mount-effect runs, `isAuthenticated` is still `false`. Line 27
 * `if (isLoading) return null` short-circuits the FIRST paint, but the
 * mount-effect callback still runs and captures the INITIAL `isAuthenticated`
 * = false → `router.push("/feed")` is NEVER called.
 *
 * After `fetchMe()` resolves → `isLoading=false`, `isAuthenticated=true` →
 * the page re-renders the form. But `useMountEffect` (empty deps) does NOT
 * re-run → the redirect never fires. A logged-in user hitting /login sees
 * the login form.
 *
 * The CLAUDE.md "Auth Architecture" claims `(auth)/layout.tsx` "redirects
 * authenticated users from login/register" — but `(auth)/layout.tsx` has NO
 * redirect-if-authenticated logic (it was moved to the page-level effect,
 * which is the broken one). No middleware exists. The `(app)/layout.tsx` SSR
 * gate only protects app pages.
 *
 * Same bug in register/page.tsx:25-27.
 *
 * Repro: provide an AuthContext that starts
 * `{isLoading:true, isAuthenticated:false}` (the real initial state) then
 * flips to `{isLoading:false, isAuthenticated:true}` after mount (mirroring
 * fetchMe resolving). Render LoginPage. Assert `router.push("/feed")` was
 * called. RED now: push is never called (the mount-effect captured the stale
 * initial false and never re-runs).
 *
 * Fix (do NOT apply here): replace the mount-only effect with one keyed on
 * `isAuthenticated`:
 *   useEffect(() => { if (isAuthenticated) router.push("/feed") },
 *     [isAuthenticated, router])
 */

import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

// Capture router.push calls.
const pushMock = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: (...args: unknown[]) => pushMock(...args),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: vi.fn(() => new URLSearchParams()),
  usePathname: vi.fn(() => "/login"),
}))

// Mock sonner toast (imported by the page for the submit handler).
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
  Toaster: () => null,
}))

// Stateful AuthContext that mirrors auth-provider.tsx initial state +
// fetchMe-resolved state. Starts {isLoading:true, isAuthenticated:false},
// then flips to {isLoading:false, isAuthenticated:true} after mount.
//
// We mock the @/components/auth-provider module so LoginPage's `useAuth()`
// gets our stateful values WITHOUT loading the real provider (which pulls in
// @tanstack/react-query, posthog, consent-provider, etc.).
//
// `vi.mock` factories run before imports and cannot reference top-level
// state declared with `let`, so we expose the state via a module-level
// accessor object that the test flips after render.
let authState: {
  user: { id: string } | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
} = {
  user: null,
  isLoading: true,
  isAuthenticated: false,
  login: vi.fn(async () => {}),
  register: vi.fn(async () => {}),
  logout: vi.fn(async () => {}),
}

// vi.mock is hoisted; the factory closes over `authState` (module-level let).
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => authState,
}))

import LoginPage from "@/app/(auth)/login/page"

describe("login page redirect-gap (repro)", () => {
  beforeEach(() => {
    pushMock.mockClear()
    authState = {
      user: null,
      isLoading: true,
      isAuthenticated: false,
      login: vi.fn(async () => {}),
      register: vi.fn(async () => {}),
      logout: vi.fn(async () => {}),
    }
  })

  it("redirects to /feed when the user is already authenticated", async () => {
    // Initial render mirrors the real AuthProvider's initial state at the
    // moment LoginPage's useMountEffect fires: isLoading=true,
    // isAuthenticated=false. The page renders null (line 27
    // `if (isLoading) return null`), but the mount-effect callback still
    // runs and captures the stale isAuthenticated=false.
    const { rerender } = render(<LoginPage />)

    // Flip the auth state to authenticated, mirroring `fetchMe()` resolving
    // in the real AuthProvider (auth-provider.tsx:60-67). This causes
    // LoginPage to re-render with isAuthenticated=true — but useMountEffect
    // (empty deps) does NOT re-run, so the redirect never fires.
    authState = {
      ...authState,
      user: { id: "user-1" },
      isLoading: false,
      isAuthenticated: true,
    }
    rerender(<LoginPage />)

    // Prove the component re-rendered with the flipped (authenticated) state
    // — the form now renders (isLoading=false). signInBtn translation =
    // "Войти" (ru.json).
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Войти|sign/i })).toBeTruthy()
    })

    // CONTRACT: a logged-in user on /login must be redirected to /feed.
    // RED now: router.push("/feed") is NEVER called — the useMountEffect
    // (empty deps) captured the INITIAL isAuthenticated=false and does not
    // re-run when the state flips to true.
    expect(pushMock).toHaveBeenCalledWith("/feed")
  })
})