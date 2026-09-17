import { renderToStaticMarkup } from "react-dom/server"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { EquipmentDiagram, PhaseExplorer, ReviewWorkspace } from "../movement-scenes"

describe("public instructional scenes", () => {
  it("changes the selected pose and matching phase explanation together", () => {
    const { container } = render(<PhaseExplorer />)
    const flight = screen.getByRole("button", { name: /Полёт/ })
    fireEvent.click(flight)
    expect(flight).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("heading", { name: "Что меняется в воздухе?" })).toBeInTheDocument()
    expect(container.querySelectorAll('.public-pose[data-selected="true"]')).toHaveLength(1)
    expect(container.querySelectorAll(".public-pose")[2]).toHaveAttribute("data-selected", "true")
    expect(renderToStaticMarkup(<PhaseExplorer />)).toMatch(/<noscript>.*Приземление.*<\/noscript>/)
  })
  it("changes frame context and the review task rather than only tab text", () => {
    const { container } = render(<ReviewWorkspace />)
    fireEvent.click(screen.getByRole("button", { name: /Следующая попытка/ }))
    expect(container.querySelector(".public-review-frame")).toHaveAttribute("data-mode", "2")
    expect(
      screen.getByRole("heading", { name: "Какую одну задачу взять на лёд?" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Сравнить следующую попытку с тем же ракурсом")).toBeInTheDocument()
  })
  it("connects sensor disclosure to the schematic source state", () => {
    const { container } = render(<EquipmentDiagram />)
    fireEvent.click(screen.getByRole("button", { name: "Данные датчика" }))
    expect(container.querySelector("svg")).toHaveAttribute("data-source", "1")
    expect(screen.getByRole("button", { name: "Видео" })).toHaveAttribute("aria-pressed", "false")
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain("калибровки")
  })
})
