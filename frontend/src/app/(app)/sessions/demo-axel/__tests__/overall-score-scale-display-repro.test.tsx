// RED repro — demo-axel page renders `overall_score` with a "/10" label
// ("из 10"). The page code at demo-axel/page.tsx:58 is:
//
//   {tSession("overallScore")}: {demo.overall_score.toFixed(1)} {tSession("scoreOutOf")}
//
// `scoreOutOf` = "из 10" (ru.json:570). The page renders the raw value with the
// "/10" label — the SAME scale-contract mismatch shape as #504 (session-detail
// page.tsx:173). #504 is the sibling: same `scoreOutOf` translation string,
// separate display site. If the #504 fix only touches sessions/[id]/page.tsx,
// demo-axel stays broken.
//
// The real backend emits overall_score as a 0..1 ratio (session_saver.py:94:
// in_range_count / len(eligible)). A perfect session → 1.0. The demo-axel page
// renders this 0..1 value with the "из 10" label → "1.0 из 10", which reads as
// 10% — a 10x display deflation. A perfect demo looks terrible on the
// marketing/onboarding surface.
//
// (The committed demo data file public/demo/session.json currently carries
// overall_score=6.8 — a 0..10 value — which masks the page-code bug for the
// stock demo. But the page CODE itself has the latent scale mismatch: it
// renders whatever value it receives with the "/10" label and no scaling. When
// the demo data is aligned to the real backend 0..1 scale, or when a perfect
// 0..1 value flows through, the page shows "1.0 из 10". This repro injects
// overall_score=1.0 — the 0..1 scale the real backend uses — to expose the
// latent page-code bug, mirroring the #504 repro.)
//
// BUG #2 (MEDIUM — scale-contract mismatch / display deflation, #504 sibling):
//   frontend/src/app/(app)/sessions/demo-axel/page.tsx:58
//       {demo.overall_score.toFixed(1)} {tSession("scoreOutOf")}
//   frontend/messages/ru.json:570  "scoreOutOf": "из 10"
//   backend/app/services/session_saver.py:94  overall_score = 0..1 ratio
//   → perfect demo overall_score=1.0 → renders "1.0 из 10" (looks 10%)
//
//   #504 (session-detail) is the same translation string, separate display
//   site. A fix for #504 must also cover demo-axel.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

import { describe, it, expect, vi, beforeEach } from "vitest"
import type { ReactElement } from "react"
import { render, screen } from "@testing-library/react"

// next/navigation: setup.ts mocks useRouter/useSearchParams/usePathname. The
// demo-axel page does not use useParams, but keep the mock consistent.
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/sessions/demo-axel",
}))

// zod v4 gotcha: named import fails under vitest/oxc transform. Remap (same
// fix as the #504 repro, in case any transitive import pulls zod).
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

// A PERFECT demo session on the REAL backend 0..1 scale: overall_score = 1.0
// (session_saver.py:94: in_range_count / len(eligible) = 1.0). The demo-axel
// page renders this 0..1 value with the "из 10" label → "1.0 из 10".
const PERFECT_DEMO = {
  id: "demo-axel",
  element_type: "axel_jump",
  status: "completed",
  // 0..1 ratio from session_saver.py:94. 1.0 = perfect (all in range).
  // The page renders toFixed(1) → "1.0" + " из 10" → "1.0 из 10" (10% look).
  overall_score: 1.0,
  created_at: "2026-06-01T00:00:00Z",
  metrics: [],
  recommendations: [],
  is_demo: true,
}

// Mock @tanstack/react-query so the page's useQuery returns the perfect demo
// immediately (isLoading=false). This avoids needing to mock global fetch.
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: PERFECT_DEMO, isLoading: false, error: null }),
}))

// Mock the data/label hooks the page calls.
vi.mock("@/hooks/use-metric-registry", () => ({
  useElementLabel: () => (code: string) => code,
}))

// Mock the heavy child components so the page renders only the score line.
// Each is used unconditionally in the demo layout; stubbing to null keeps the
// render light and isolates the score-display string under test.
vi.mock("@/components/demo/demo-badge", () => ({ DemoBadge: () => null }))
vi.mock("@/components/demo/upload-cta-banner", () => ({ UploadCtaBanner: () => null }))
vi.mock("@/components/skeleton-detail", () => ({ SkeletonDetail: () => null }))
vi.mock("@/components/session/metric-row", () => ({ MetricRow: () => null }))

// @/i18n is mocked in setup.ts to return REAL ru strings from ru.json, so
// tSession("overallScore") → "Общая оценка" and tSession("scoreOutOf") → "из 10".

import DemoSessionPage from "@/app/(app)/sessions/demo-axel/page"

describe("demo-axel overall_score scale display (repro)", () => {
  beforeEach(() => {
    if (typeof window !== "undefined") {
      window.localStorage.clear()
    }
  })

  it("does NOT render a perfect demo (overall_score=1.0) as '1.0 из 10'", () => {
    // The real backend emits overall_score as a 0..1 ratio (session_saver.py:94).
    // A perfect demo → 1.0. The demo-axel page renders it with the "из 10"
    // label (page.tsx:58) → "1.0 из 10", which reads as 10% — a 10x display
    // deflation on the marketing/onboarding surface.
    //
    // CONTRACT: the displayed score for a perfect demo must NOT be "1.0 из 10".
    // Expected: either "10.0 из 10" (if the value is scaled to /10) or a
    // percentage like "100%" (matching recent-activity.tsx:43). RED now: the
    // rendered text is "1.0 из 10".
    render((<DemoSessionPage />) as unknown as ReactElement)

    const bodyText = document.body.textContent ?? ""

    expect(bodyText).not.toMatch(/1\.0\s*из\s*10/)
  })
})
