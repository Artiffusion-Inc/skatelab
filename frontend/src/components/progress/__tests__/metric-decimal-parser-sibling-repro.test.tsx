// RED repro — #446-class decimal-parser sibling bug in 3 progress consumers.
//
// PersonalRecords (personal-records.tsx:47) was FIXED in #446 to parse the
// backend's Python format-spec (e.g. ".0f", ".2f") via
//   Number(mdef.format?.match(/\d+(?=f)/)?.[0] ?? 2)
// and render `value.toFixed(parsedDecimals)`. Three sibling consumers were
// NOT updated — each invented its own heuristic that ignores `format`:
//
//   1. metric-card.tsx:49
//        value.toFixed(direction === "lower" ? 1 : 2)
//        → uses `direction` to pick decimals, IGNORES `format`.
//          A .0f metric with direction="higher" (rotation_speed=540) renders
//          "540.00" instead of "540". A .3f metric renders 2 decimals
//          (precision loss).
//
//   2. metric-deep-dive.tsx:69 and :90
//        latestValue.toFixed(metricDef?.format === "pct" ? 1 : 3)
//        → `format` is NEVER "pct" (backend emits .2f/.1f/.0f/.3f), so the
//          "pct" branch is DEAD and it always renders 3 decimals.
//          rotation_speed (.0f) renders "540.000"; airtime (.2f) renders
//          "0.850" instead of "0.85".
//
//   3. trend-chart.tsx:69
//        data.current_pr.toFixed(3)
//        → always 3 decimals, ignores format.
//
// Backend `format` (metrics_registry.py: .0f/.1f/.2f/.3f) is the single source
// of truth, ignored in all 3. Same value renders "540" in PersonalRecords
// (fixed) vs "540.00" in MetricCard vs "540.000" in MetricDeepDive/TrendChart —
// visible inconsistency.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it, vi } from "vitest"
import { server } from "@/test/server"
import { render, screen } from "@/test/test-utils"
import { MetricCard } from "../metric-card"
import { MetricDeepDive } from "../metric-deep-dive"

// zod v4 gotcha: connections/metrics modules use `import { z } from "zod"`
// (named import) which fails under vitest/oxc transform. Remap so named +
// default both resolve. (Mirrors sessions-hooks-repro.test.tsx pattern.)
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

// Registry fixture using REAL backend format strings
// (backend/app/metrics_registry.py): rotation_speed → ".0f", direction
// "higher". A value of 540 (deg/s) must render "540" (zero decimals), not
// "540.00" (MetricCard) or "540.000" (MetricDeepDive).
const FIXTURE_REGISTRY = {
  rotation_speed: {
    name: "rotation_speed",
    label_ru: "Скорость вращения",
    unit: "deg/s",
    format: ".0f",
    direction: "higher",
    element_types: ["3A"],
    ideal_range: [300, 600],
  },
}

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe("MetricCard decimal-parser sibling (#446-class, RED repro)", () => {
  it("renders a .0f metric with direction='higher' as '540.00' instead of '540' (ignores format, uses direction)", () => {
    // MetricCard has NO `format` prop (MetricCardProps interface lacks it),
    // and element-detail.tsx never passes format — so the component CANNOT
    // respect the backend .0f spec. It hardcodes
    //   value.toFixed(direction === "lower" ? 1 : 2)
    // → direction="higher" → toFixed(2) → "540.00".
    withProviders(<MetricCard label="Скорость вращения" value={540} format=".0f" unit="deg/s" />)

    const rendered = screen.getByText(/540/)
    // Capture the actual rendered text for the receipt.
    // eslint-disable-next-line no-console
    console.log("[MetricCard] rendered value:", JSON.stringify(rendered.textContent))

    // CONTRACT: a .0f metric value of 540 must render "540", NOT "540.00".
    // RED now: renders "540.00" (toFixed(2) from the direction-based heuristic).
    expect(rendered.textContent).toBe("540")
  })
})

describe("MetricDeepDive decimal-parser sibling (#446-class, RED repro)", () => {
  it("renders a .0f metric value as '540.000' instead of '540' (dead 'pct' branch, always 3 decimals)", async () => {
    // Mock the 3 endpoints MetricDeepDive queries: registry, trend, prs.
    // (diagnostics optional — component tolerates undefined findings.)
    server.use(
      http.get("*/metrics/registry", () => HttpResponse.json(FIXTURE_REGISTRY)),
      http.get("*/metrics/trend*", () =>
        HttpResponse.json({
          metric_name: "rotation_speed",
          element_type: "3A",
          data_points: [
            { date: "2026-06-28", value: 520, session_id: "s1", is_pr: false },
            { date: "2026-06-29", value: 540, session_id: "s2", is_pr: true },
          ],
          trend: "improving",
          current_pr: 540,
          reference_range: { min: 300, max: 600 },
        }),
      ),
      http.get("*/metrics/prs*", () =>
        HttpResponse.json({
          prs: [
            { element_type: "3A", metric_name: "rotation_speed", value: 540, session_id: "s2" },
          ],
        }),
      ),
      http.get("*/metrics/diagnostics*", () => HttpResponse.json({ user_id: "u1", findings: [] })),
    )

    withProviders(<MetricDeepDive elementId="3A" metricName="rotation_speed" />)

    // The header value (line 69) renders
    //   latestValue.toFixed(metricDef?.format === "pct" ? 1 : 3)
    // inside <p className="text-2xl font-bold tabular-nums">. format is ".0f"
    // (never "pct") → toFixed(3) → "540.000". Target the header <p> directly
    // (the only text-2xl bold tabular-nums value node) to avoid matching the
    // PR row / reference-range bar which also render 540.000.
    const header = await screen.findByText((content, element) => {
      if (!element) return false
      const cls = element.getAttribute("class") ?? ""
      return cls.includes("text-2xl") && cls.includes("font-bold") && /540/.test(content)
    })
    // eslint-disable-next-line no-console
    console.log("[MetricDeepDive] header rendered value:", JSON.stringify(header.textContent))

    // CONTRACT: a .0f metric value of 540 must render "540", NOT "540.000".
    // RED now: renders "540.000" (toFixed(3) — the "pct" branch is dead).
    expect(header.textContent).toBe("540deg/s")
  })
})
