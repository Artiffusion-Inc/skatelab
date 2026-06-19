import { describe, expect, it } from "vitest"
import { render, screen } from "@/test/test-utils"
import { ScoreBreakdown } from "./score-breakdown"
import { mockScore } from "@/lib/mocks/skating-analyzer"

describe("ScoreBreakdown", () => {
  it("renders overall score in header", () => {
    render(<ScoreBreakdown score={mockScore} />)
    expect(screen.getByText(/overallScore/)).toBeTruthy()
  })

  it("renders data quality and reliability labels", () => {
    render(<ScoreBreakdown score={mockScore} />)
    expect(screen.getByText(/dataQuality/)).toBeTruthy()
    expect(screen.getByText(/skeletonReliability/)).toBeTruthy()
  })

  it("renders chart wrapper", () => {
    render(<ScoreBreakdown score={mockScore} />)
    expect(document.querySelector(".h-64")).toBeTruthy()
  })
})
