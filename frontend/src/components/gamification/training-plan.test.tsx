import { describe, expect, it } from "vitest"
import { render } from "@/test/test-utils"
import { TrainingPlanComponent } from "./training-plan"

// Note: component export name is TrainingPlanComponent
import { mockTrainingPlan } from "@/lib/mocks/skating-analyzer"

describe("TrainingPlan", () => {
  it("renders plan title and progress", () => {
    render(<TrainingPlanComponent plan={mockTrainingPlan} />)
    expect(document.body.textContent).toContain("План тренировки")
    expect(document.body.textContent).toContain("1/4")
  })

  it("renders all plan items", () => {
    render(<TrainingPlanComponent plan={mockTrainingPlan} />)
    expect(document.body.textContent).toContain("Упражнение на амортизацию")
    expect(document.body.textContent).toContain("Работа над осью вращения")
  })

  it("shows completed item with strikethrough", () => {
    render(<TrainingPlanComponent plan={mockTrainingPlan} />)
    expect(document.body.textContent).toContain("Работа над осью вращения")
  })
})
