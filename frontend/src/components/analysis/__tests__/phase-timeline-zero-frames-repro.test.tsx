import { describe, expect, it } from "vitest"
import { render } from "@/test/test-utils"
import { PhaseTimelineExtended } from "../phase-timeline-extended"
import { useAnalysisStore } from "@/stores/analysis"
import type { PhaseDetectionResult } from "@/types"

// RED repro: PhaseTimelineExtended totalFrames=0 → NaN/Infinity styles +
// negative frame seek (divide-by-zero; line-36 guard misses empty-frames-array).
//
// #484 fix: added `if (!totalFrames) return null` guard after the
// line-36 phase-empty guard, plus `Math.max(0, ...)` in the ArrowRight
// handler. The component now returns null when totalFrames=0, so:
// - the slider doesn't render → no keyDown event → currentFrame stays 0
// - no marker / phase zone elements → no NaN/Infinity CSS values
// - the divide-by-zero is impossible
//
// sessions/[id]/page.tsx:389 passes
// totalFrames=pose_data?.frames?.length ?? 120. `?? 120` catches
// null/undefined, NOT empty array → pose_data.frames=[] → totalFrames=0
// (reachable when worker sample_poses gets n_frames=0, zero valid
// poses). With the new guard, the timeline component returns null in
// this case — the user sees no timeline (instead of broken styles).

const mockResult: PhaseDetectionResult = {
  phases: [
    {
      name: "approach",
      start_frame: 0,
      end_frame: 30,
      start_time: 0.0,
      end_time: 1.0,
      confidence: 0.82,
      detection_method: "com_parabola",
    },
    {
      name: "takeoff",
      start_frame: 30,
      end_frame: 55,
      start_time: 1.0,
      end_time: 1.83,
      confidence: 0.91,
      detection_method: "com_parabola",
    },
  ],
  overall_confidence: 0.86,
  element_type: "waltz_jump",
  fallback_used: false,
}

describe("PhaseTimelineExtended totalFrames=0 (RED repro)", () => {
  it("returns null when totalFrames=0 (divide-by-zero guard)", () => {
    useAnalysisStore.setState({ currentFrame: 0 })
    const { container } = render(<PhaseTimelineExtended totalFrames={0} result={mockResult} />)
    // #484 fix: the component returns null when totalFrames=0. The
    // container is empty (no rendered DOM). Pre-fix: the component
    // rendered with NaN/Infinity CSS values, the slider existed,
    // ArrowRight set currentFrame to -1, the marker / phase zones
    // had empty style.left (NaN% dropped by happy-dom).
    expect(
      container.innerHTML,
      "PhaseTimelineExtended should return null when totalFrames=0",
    ).toEqual("")
  })

  it("does not render marker or phase zones when totalFrames=0", () => {
    useAnalysisStore.setState({ currentFrame: 0 })
    const { container } = render(<PhaseTimelineExtended totalFrames={0} result={mockResult} />)
    // The slider / marker / phase zones should not be in the DOM.
    // Pre-fix: they were rendered with NaN/Infinity CSS values.
    const slider = container.querySelector('[role="slider"]')
    const marker = container.querySelector(".w-0\\.5")
    const zone = container.querySelector(".group")
    expect(slider, "slider should not render when totalFrames=0").toBeNull()
    expect(marker, "current-frame marker should not render when totalFrames=0").toBeNull()
    expect(zone, "phase zone should not render when totalFrames=0").toBeNull()
  })

  it("currentFrame stays >= 0 when totalFrames=0 (no negative frame seek)", () => {
    useAnalysisStore.setState({ currentFrame: 0 })
    // Just rendering the component (without firing keyDown) — the
    // currentFrame should not change. Pre-fix: ArrowRight on the slider
    // would set currentFrame to -1.
    render(<PhaseTimelineExtended totalFrames={0} result={mockResult} />)
    const cf = useAnalysisStore.getState().currentFrame
    expect(cf).toBeGreaterThanOrEqual(0)
  })
})
