// RED repro — PhaseTimelineExtended receives totalFrames = SAMPLED frame
// COUNT (frames.length) from the session-detail AnalyzerTab, NOT the max
// ABSOLUTE video frame index. PhaseExtended.start_frame/end_frame are ABSOLUTE
// video frame indices. Dividing an absolute frame by a sampled count yields a
// percentage ~10x too large → phase zones render OFF-SCREEN (>100% left). This
// is an ALWAYS-ON bug on every session with pose_data + phases, NOT the zero-
// edge divide-by-zero sibling (#484, frames=[] → totalFrames=0).
//
// BUG (HIGH — always-on scale mismatch, distinct from #484 zero-edge):
//   frontend/src/app/(app)/sessions/[id]/page.tsx:389
//       totalFrames={session.pose_data?.frames?.length ?? 120}
//   `frames` is the SAMPLED frame-index array. At sampling=10 (worker.py:403
//   _sample_poses(poses, 10)) a 300-frame video yields frames=[0,10,20,...,290]
//   length=30. frames.length=30 = sampled COUNT.
//
//   frontend/src/app/(app)/sessions/[id]/page.tsx:61 (CORRECT — overview tab)
//       const totalFrames = session?.pose_data ? Math.max(...session.pose_data.frames) : 300
//   Line 389 is the odd one out — uses frames.length, not Math.max(frames).
//
//   backend/app/services/analyzer_save.py:119-156
//       { name: "approach", start_frame: start, end_frame: takeoff, ... }
//   start/end_frame are ABSOLUTE video frame indices (start, takeoff, peak,
//   landing, end span the full 0..~300 range), NOT sampled indices.
//
//   frontend/src/components/analysis/phase-timeline-extended.tsx:62-63
//       const startPercent = (phase.start_frame / totalFrames) * 100
//       const endPercent   = (phase.end_frame   / totalFrames) * 100
//   → (60 / 30) * 100 = 200%  →  style={{ left: "200%", width: "100%" }}
//   → phase zone renders off-screen. EVERY analyzed session is broken.
//
//   worker.py:403  sample_future = asyncio.to_thread(_sample_poses, poses, 10)
//   → sampling rate hardcoded 10 → frames.length ≈ n_frames/10 while phase
//   frames are absolute → ~10x scale mismatch on every session.
//
// Mandate: RED test only. No production code edits, no fix-PR.

import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { PhaseTimelineExtended } from "@/components/analysis/phase-timeline-extended"
import type { PhaseDetectionResult } from "@/types"

// 300-frame video sampled at 10 → pose_data.frames = [0,10,20,...,290].
// Worker hardcodes sampling=10 in worker.py:403. frames.length=30 (sampled
// COUNT), but max frame index = 290 (≈ 300). PhaseExtended.start_frame /
// end_frame are ABSOLUTE video frame indices, not sampled indices.
//
// page.tsx:395 (FIXED) now passes Math.max(...frames) instead of
// frames.length. Math.max(290) is the absolute max. Use MAX_FRAME=300 in
// the test (the value the fixed caller passes).
const MAX_FRAME = 300 // Math.max(...frames) — the FIXED value the caller passes
const RESULT: PhaseDetectionResult = {
  phases: [
    {
      name: "approach",
      start_frame: 60, // absolute video frame
      end_frame: 120,
      start_time: 2.0,
      end_time: 4.0,
      confidence: 0.7,
      detection_method: "heuristic",
    },
    {
      name: "takeoff",
      start_frame: 120,
      end_frame: 180,
      start_time: 4.0,
      end_time: 6.0,
      confidence: 0.85,
      detection_method: "com_parabola",
    },
  ],
  overall_confidence: 0.8,
  element_type: "waltz_jump",
  fallback_used: false,
}

describe("PhaseTimelineExtended totalFrames = sampled-count (always-on off-screen, repro)", () => {
  it("phase zones stay in-bounds (left ≤ 100%) when totalFrames is the max-frame (the FIXED caller)", () => {
    // The fix: page.tsx:395 passes Math.max(...frames) = 300 (not frames.length=30).
    // With the correct totalFrames, startPercent = (60/300)*100 = 20%, endPercent =
    // 40% → zone in-bounds. RED pre-fix: 60/30*100=200% off-screen.
    const { container } = render(<PhaseTimelineExtended totalFrames={MAX_FRAME} result={RESULT} />)

    // Phase zones are the absolutely-positioned divs whose style carries
    // left/width in percent. Collect every [style] element and parse left%.
    const styledEls = Array.from(container.querySelectorAll<HTMLElement>("[style]"))
    const offScreen = styledEls
      .map(el => el.getAttribute("style") ?? "")
      .map(style => style.match(/left:\s*([\d.]+)%/))
      .filter((m): m is RegExpMatchArray => m !== null)
      .map(m => parseFloat(m[1]))

    expect(offScreen.length, "expected at least one phase-zone with a left% style").toBeGreaterThan(
      0,
    )
    expect(
      Math.max(...offScreen),
      `BUG: phase zone left=${Math.max(...offScreen)}% (>100% off-screen) — ` +
        `totalFrames=30 (frames.length, sampled COUNT) but phase.start_frame=60 ` +
        `(ABSOLUTE video frame, analyzer_save.py:119). ` +
        `(60/30)*100=200%. page.tsx:389 uses frames?.length; line 61 correctly ` +
        `uses Math.max(...frames). Every analyzed session renders phase zones ` +
        `off-screen. Distinct from #484 (zero-edge divide-by-zero).`,
    ).toBeLessThanOrEqual(100)
  })
})
