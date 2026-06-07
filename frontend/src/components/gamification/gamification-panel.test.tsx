import { describe, expect, it } from "vitest"
import { render } from "@/test/test-utils"
import { GamificationPanel } from "./gamification-panel"
import { mockUserLevel, mockSkills } from "@/lib/mocks/skating-analyzer"

describe("GamificationPanel", () => {
  it("renders level title", () => {
    render(<GamificationPanel level={mockUserLevel} skills={mockSkills} />)
    expect(document.body.textContent).toContain("Уровень 3")
  })

  it("renders XP progress", () => {
    render(<GamificationPanel level={mockUserLevel} skills={mockSkills} />)
    expect(document.body.textContent).toContain("340")
    expect(document.body.textContent).toContain("700")
  })

  it("renders 9 skill cards", () => {
    render(<GamificationPanel level={mockUserLevel} skills={mockSkills} />)
    expect(document.querySelectorAll('[title]')).toHaveLength(9)
  })
})
