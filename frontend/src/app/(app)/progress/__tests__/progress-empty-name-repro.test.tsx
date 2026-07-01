/**
 * RED repro — ProgressPage student list crashes (TypeError) on empty to_user_name.
 *
 * progress/page.tsx:118 uses the SAME pattern #477 fixed in StudentCard:
 *   {(conn.to_user_name ?? "?")[0].toUpperCase()}
 * `??` catches null/undefined but NOT the empty string: when to_user_name === ""
 *   ("" ?? "?")[0] === ""[0] === undefined → undefined.toUpperCase() throws.
 * The whole coach "students" view breaks for any coach with one empty-name
 * student connection. #477 fixed StudentCard but missed this page (sibling).
 *
 * Render the real ProgressPage with mocked data hooks returning one active
 * coaching connection whose to_user_name === "". The coach-view mode is forced
 * to "students" via localStorage so the crashing branch renders.
 */

import { describe, expect, it, vi, beforeEach } from "vitest"
import { render } from "@testing-library/react"

// useConnections returns one active coaching connection with an EMPTY name.
vi.mock("@/lib/api/connections", () => ({
  useConnections: () => ({
    data: {
      connections: [
        {
          id: "c1",
          from_user_id: "coach-1",
          to_user_id: "student-1",
          to_user_name: "", // EMPTY — the trigger
          connection_type: "coaching",
          status: "active",
          initiated_by: "coach-1",
          created_at: "2026-06-29T10:00:00Z",
          ended_at: null,
          from_user_name: "Coach",
        },
      ],
    },
    status: "success",
    error: null,
  }),
  useInviteConnection: () => vi.fn(),
  useAcceptConnection: () => vi.fn(),
  useEndConnection: () => vi.fn(),
}))

// useDiagnostics returns a success result with at least one finding so the
// element-cards branch is reachable, but the students branch renders first
// because viewMode === "students".
vi.mock("@/lib/api/metrics", () => ({
  useDiagnostics: () => ({
    data: { findings: [{ severity: "warning", element: "waltz_jump" }] },
    status: "success",
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock("@/hooks/use-metric-registry", () => ({
  useElementLabel: () => (code: string) => code,
  useElementMap: () => ({ waltz_jump: {} }),
}))

// Mock the auth/api layer transitively imported by onboarding/skeleton/error
// components — avoids zod v4 resolution failing under vitest/happy-dom
// (unrelated infra-debt, not the bug under test).
vi.mock("@/lib/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  refreshToken: vi.fn(),
  fetchMe: vi.fn(),
  updateProfile: vi.fn(),
}))
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: { id: "coach-1" }, isAuthenticated: true, isLoading: false }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

import ProgressPage from "@/app/(app)/progress/page"

describe("ProgressPage empty to_user_name crash (RED repro, #477 sibling)", () => {
  beforeEach(() => {
    // Force the "students" view so the crashing avatar-initial branch renders.
    vi.stubGlobal(
      "localStorage",
      (() => {
        let mode = "students"
        return {
          getItem: (k: string) => (k === "coach_view_mode" ? mode : null),
          setItem: (k: string, v: string) => {
            if (k === "coach_view_mode") mode = v
          },
          removeItem: vi.fn(),
          clear: vi.fn(),
          key: vi.fn(),
          length: 0,
        }
      })(),
    )
  })

  it('BUG: students view crashes on empty to_user_name (RED — `??` misses "")', () => {
    // CONTRACT: the coach students list must render with an empty-name student.
    // RED now: ("" ?? "?")[0].toUpperCase() throws TypeError → render fails.
    // (After the `??` -> `||` fix this passes — RED->GREEN.)
    expect(() => render(<ProgressPage />)).not.toThrow()
  })
})
