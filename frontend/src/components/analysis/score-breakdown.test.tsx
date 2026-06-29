import { describe, expect, it } from "vitest"
import { render, screen } from "@/test/test-utils"
import { ScoreBreakdown } from "./score-breakdown"
import { mockScore } from "@/lib/mocks/skating-analyzer"

describe("ScoreBreakdown", () => {
  it("renders overall score in header", () => {
    render(<ScoreBreakdown score={mockScore} />)
    // analysis.overallScore = "Общая оценка: {score} / 10"; mockScore.overall=6.3
    expect(screen.getByText(/Общая оценка: 6\.3 \/ 10/)).toBeTruthy()
  })

  it("renders data quality and reliability labels", () => {
    render(<ScoreBreakdown score={mockScore} />)
    // analysis.dataQuality = "Качество данных: {quality}"; quality_good = "хорошее"
    expect(screen.getByText(/Качество данных: хорошее/)).toBeTruthy()
    // analysis.skeletonReliability = "Скелет: {reliability}"; reliability_reliable = "надёжный"
    expect(screen.getByText(/Скелет: надёжный/)).toBeTruthy()
  })

  it("renders chart wrapper", () => {
    render(<ScoreBreakdown score={mockScore} />)
    expect(document.querySelector(".h-64")).toBeTruthy()
  })
})
