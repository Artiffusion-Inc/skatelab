// RED repro — MetricRow + session-card respect backend registry format (#495
// mirror, #510). After the fix: MetricRow takes a `format` prop; session-card
// reads the registry format. Tests pass the format and assert the decimals.

import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@/test/test-utils"
import { MetricRow } from "../metric-row"
import { SessionCard } from "../session-card"

// zod v4 gotcha: hooks/use-metric-registry (imported by session-card) uses
// `import { z } from "zod"` (named import) which fails under vitest/oxc
// transform. Remap so named + default both resolve.
vi.mock("zod", async () => {
  const actual = await vi.importActual<typeof import("zod")>("zod")
  return { ...actual, default: actual, z: actual }
})

// session-card reads the registry via useMetricRegistry (react-query). Mock
// it so max_height resolves to a .3f entry — the contract under test.
vi.mock("@/hooks/use-metric-registry", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-metric-registry")>(
    "@/hooks/use-metric-registry",
  )
  return {
    ...actual,
    useMetricRegistry: () => ({
      data: {
        max_height: { name: "max_height", label_ru: "Макс. высота", unit: "норм", format: ".3f" },
      },
    }),
  }
})

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe("MetricRow respects backend format prop (#495 mirror, #510)", () => {
  it("renders a .3f metric value 0.423 as '0.423' (not toFixed(2) '0.42')", () => {
    withProviders(
      <MetricRow
        name="max_height"
        label="Макс. высота"
        value={0.423}
        unit="норм"
        format=".3f"
        isInRange={true}
        isPr={true}
        prevBest={0.401}
        direction="higher"
      />,
    )

    const valueNode = screen.getByText(/0\.4/)
    // CONTRACT: a .3f metric renders "0.423", not the toFixed(2) "0.42".
    // RED before fix (no format prop): renders "0.42".
    expect(valueNode.textContent).toContain("0.423")
    expect(valueNode.textContent).not.toBe("0.42 норм")
  })

  it("renders a .0f metric value 540 as '540' (not toFixed(2) '540.00')", () => {
    withProviders(
      <MetricRow
        name="rotation_speed"
        label="Скорость вращения"
        value={540}
        unit="deg/s"
        format=".0f"
        isInRange={true}
        isPr={false}
        prevBest={null}
        direction="higher"
      />,
    )

    const valueNode = screen.getByText(/540/)
    // CONTRACT: a .0f metric renders "540", not the toFixed(2) "540.00".
    expect(valueNode.textContent).toBe("540 deg/s")
  })
})

describe("SessionCard reads registry format for the metric strip (#495 mirror, #510)", () => {
  it("renders a .3f metric value 0.423 as '0.423' (not toFixed(2) '0.42')", () => {
    const session = {
      id: "sess-1",
      user_id: "u-1",
      element_type: "flip",
      video_key: "v/1.mp4",
      video_url: "https://cdn/v/1.mp4",
      processed_video_key: null,
      processed_video_url: null,
      pose_data: null,
      frame_metrics: null,
      status: "completed",
      error_message: null,
      phases: null,
      recommendations: [],
      overall_score: 0.88,
      process_task_id: null,
      imu_left_key: null,
      imu_right_key: null,
      manifest_key: null,
      created_at: "2026-06-01T00:00:00Z",
      processed_at: "2026-06-01T00:10:00Z",
      metrics: [
        {
          id: "m1",
          metric_name: "max_height",
          metric_value: 0.423,
          unit: "норм",
          is_pr: false,
          is_in_range: true,
          prev_best: null,
          reference_value: null,
        },
      ],
      timeline: {
        segments: [],
        segmentation_confidence: null,
        segmentation_status: "done",
      },
      segmentation_status: "done",
    }

    withProviders(<SessionCard session={session as never} />)

    const metricNode = screen.getByText(/max_height/)
    // CONTRACT: the metric strip renders "0.423", not toFixed(2) "0.42".
    // RED before fix (no registry lookup): renders "max_height: 0.42".
    expect(metricNode.textContent).toContain("0.423")
    expect(metricNode.textContent).not.toBe("max_height: 0.42")
  })
})
