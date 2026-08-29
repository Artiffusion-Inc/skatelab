/**
 * RED→GREEN repro tests for issues #833–#835 (progress visualization audit).
 *
 * #833 TrendChart Line stroke `hsl(var(--primary))` wraps OKLCH token → invalid CSS color
 * #834 ReferenceRangeBar clamp collapses out-of-range values to edge — magnitude hidden
 * #835 MetricCard renders "0.00" for no-PR metrics — no empty state
 *
 * Source-asserting for #833/#834 (pure rendering/source contracts) and
 * behavioral render for #835 (empty state).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@/test/test-utils"
import { readFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { MetricCard } from "../metric-card"

const PROGRESS_DIR = join(dirname(new URL(import.meta.url).pathname), "..")
const COMPONENTS_DIR = join(PROGRESS_DIR, "..")

function readSrc(name: string): string {
  return readFileSync(join(PROGRESS_DIR, name), "utf-8")
}

// zod v4 named-import gotcha (mirrors sibling test).
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

// ---------------------------------------------------------------------------
// #833: TrendChart Line stroke must not wrap OKLCH token in hsl()
// ---------------------------------------------------------------------------

describe("#833 TrendChart stroke uses raw OKLCH token", () => {
  it("trend-chart no longer wraps var(--primary) in hsl()", () => {
    const src = readSrc("trend-chart.tsx")
    // The malformed pattern: stroke="hsl(var(--primary))" → hsl(oklch(...))
    // invalid CSS color → recharts renders the line transparent. Check the
    // active stroke attribute, not comments that mention the old pattern.
    const strokeMatches = [...src.matchAll(/stroke="([^"]*)"/g)]
    const primaryStrokes = strokeMatches.map(m => m[1]).filter(s => s.includes("primary"))
    expect(primaryStrokes.length, "expected a stroke referencing --primary").toBeGreaterThan(0)
    for (const s of primaryStrokes) {
      expect(s, `stroke="${s}" must not wrap --primary in hsl()`).not.toMatch(
        /^hsl\(var\(--primary\)\)$/,
      )
      expect(s).toMatch(/^oklch\(var\(--primary\)\)$/)
    }
  })

  it("trend-chart is the only hsl(var(--primary)) offender — siblings already OK", () => {
    // Spot-check the sibling consumers named in the issue agree on OKLCH.
    const frameMetrics = readFileSync(
      join(COMPONENTS_DIR, "analysis", "frame-metrics-chart.tsx"),
      "utf-8",
    )
    // Active stroke referencing --primary must be OKLCH, not hsl-wrapped.
    const strokeMatches = [...frameMetrics.matchAll(/stroke="([^"]*)"/g)]
    const primaryStrokes = strokeMatches.map(m => m[1]).filter(s => s.includes("primary"))
    expect(primaryStrokes.length).toBeGreaterThan(0)
    for (const s of primaryStrokes) {
      expect(s).toMatch(/^oklch\(var\(--primary\)\)$/)
      expect(s).not.toMatch(/^hsl\(var\(--primary\)\)$/)
    }
  })
})

// ---------------------------------------------------------------------------
// #834: ReferenceRangeBar must not clamp the value marker to [0,100]
// ---------------------------------------------------------------------------

describe("#834 ReferenceRangeBar does not collapse out-of-range magnitude", () => {
  it("source computes value position without Math.min/Math.max clamp", () => {
    const src = readSrc("reference-range-bar.tsx")
    // The buggy pct: clamp(((v - min) / range) * 100) → min/max collapse.
    // The value-marker pct must be unclamped. (Ideal-band fill may still
    // clamp — that's a rectangle, not the marker.)
    expect(src).not.toMatch(/const\s+pct\s*=\s*\(v[^)]*\)\s*=>\s*clamp\(/)
    // The value marker uses a raw (unclamped) percentage.
    // Look for valuePct derived from an unclamped computation.
    expect(src).toMatch(/valuePct/)
  })

  it("bar container allows the marker to draw past the edges (overflow-visible)", () => {
    const src = readSrc("reference-range-bar.tsx")
    // overflow-visible lets the marker sit past bar edges when value is
    // outside [min, max] — a 2x overshoot visibly further than a 1.5x one.
    expect(src).toMatch(/overflow-visible/)
  })
})

// ---------------------------------------------------------------------------
// #835: MetricCard empty state when no PR (hasData=false)
// ---------------------------------------------------------------------------

describe("#835 MetricCard empty state for no-PR metrics", () => {
  it("renders an em-dash placeholder when hasData=false (not '0.00')", () => {
    withProviders(
      <MetricCard label="Скорость вращения" value={0} unit="deg/s" format=".2f" hasData={false} />,
    )

    // Must NOT render a measured "0.00" with unit.
    expect(screen.queryByText("0.00")).toBeNull()
    expect(screen.queryByText("deg/s")).toBeNull()
    // Must render the empty placeholder.
    expect(screen.getByText("—")).toBeTruthy()
  })

  it("renders the measured value + unit when hasData=true (regression guard)", () => {
    withProviders(
      <MetricCard label="Скорость вращения" value={540} unit="deg/s" format=".0f" hasData />,
    )
    expect(screen.getByText("540")).toBeTruthy()
    expect(screen.getByText("deg/s")).toBeTruthy()
    expect(screen.queryByText("—")).toBeNull()
  })

  it("MetricCard accepts a hasData prop (interface widening)", () => {
    const src = readSrc("metric-card.tsx")
    expect(src).toMatch(/hasData\??\s*:/)
    // Default must be truthy so existing callers without hasData still render
    // the value (no behavior change for the happy path).
    expect(src).toMatch(/hasData\s*=\s*true/)
  })

  it("element-detail threads hasData from isPr (no-PR → empty state)", () => {
    const src = readSrc("element-detail.tsx")
    expect(src).toMatch(/hasData=\{card\.isPr\}/)
  })
})
