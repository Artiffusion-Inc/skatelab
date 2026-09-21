import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { AnalysisReadiness, getAnalysisAvailability } from "./analysis-readiness"

describe(getAnalysisAvailability, () => {
  it("marks a complete 2D result while keeping 3D explicit", () => {
    expect(getAnalysisAvailability({ hasVideo: true, hasPoseData: true, metricCount: 4 })).toEqual({
      missing: [],
      has3d: false,
    })
  })

  it("lists the parts that are missing from a partial result", () => {
    expect(
      getAnalysisAvailability({ hasVideo: false, hasPoseData: false, metricCount: 0 }),
    ).toEqual({
      missing: ["video", "pose", "metrics"],
      has3d: false,
    })
  })
})

describe(AnalysisReadiness, () => {
  it("shows the experimental status and missing-result warning", () => {
    render(<AnalysisReadiness hasVideo={false} hasPoseData metricCount={0} />)

    expect(screen.getByText("Экспериментальный анализ")).toBeInTheDocument()
    expect(screen.getByText(/Результат неполный/)).toBeInTheDocument()
    expect(screen.getByText(/3D-оценка недоступна/)).toBeInTheDocument()
    expect(screen.getByText("Видео").parentElement).toHaveTextContent(/Видео.*недоступно/)
  })
})
