import { describe, expect, it } from "vitest"
import { render } from "@/test/test-utils"
import { PhaseTimelineExtended } from "./phase-timeline-extended"
import { mockPhases } from "@/lib/mocks/skating-analyzer"

describe("PhaseTimelineExtended", () => {
  it("renders without crashing", () => {
    render(<PhaseTimelineExtended totalFrames={120} result={mockPhases} />)
    expect(document.querySelector('[role="slider"]')).toBeTruthy()
  })

  it("returns null when no result", () => {
    const { container } = render(<PhaseTimelineExtended totalFrames={120} result={null} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders 5 phase zones", () => {
    render(<PhaseTimelineExtended totalFrames={120} result={mockPhases} />)
    const zones = document.querySelectorAll('[title*="confidence"]')
    expect(zones.length).toBe(5)
  })
})
