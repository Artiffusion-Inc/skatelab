import { renderToStaticMarkup } from "react-dom/server"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useSearchParams } from "next/navigation"
import { EquipmentDiagram, PhaseExplorer, ReviewWorkspace } from "../movement-scenes"

describe("public instructional scenes", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/")
    vi.mocked(useSearchParams).mockImplementation(
      () => new URLSearchParams(window.location.search) as ReturnType<typeof useSearchParams>,
    )
  })
  it("changes the selected pose and matching phase explanation together", () => {
    const { container, rerender } = render(<PhaseExplorer />)
    const flight = screen.getByRole("button", { name: /Полёт/ })
    fireEvent.click(flight)
    expect(window.location.search).toBe("?phase=3")
    rerender(<PhaseExplorer />)
    expect(flight).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("heading", { name: "Что меняется в воздухе?" })).toBeInTheDocument()
    expect(container.querySelectorAll('.public-pose[data-selected="true"]')).toHaveLength(1)
    expect(container.querySelectorAll(".public-pose")[2]).toHaveAttribute("data-selected", "true")
    expect(renderToStaticMarkup(<PhaseExplorer />)).toMatch(/<noscript>.*Приземление.*<\/noscript>/)
  })
  it("restores a phase from the URL and rejects invalid phase values", () => {
    window.history.replaceState(null, "", "/?phase=2#story")
    const { rerender } = render(<PhaseExplorer />)
    expect(screen.getByRole("button", { name: /Отталкивание/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    window.history.replaceState(null, "", "/?phase=99#story")
    rerender(<PhaseExplorer />)
    expect(screen.getByRole("button", { name: /Подготовка/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("changes frame context and the review task rather than only tab text", () => {
    const { container } = render(<ReviewWorkspace />)
    fireEvent.click(screen.getByRole("button", { name: /Сравнить попытки/ }))
    expect(container.querySelector(".public-review-frame")).toHaveAttribute("data-mode", "2")
    expect(
      screen.getByRole("heading", { name: "Что изменилось в следующей попытке?" }),
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
