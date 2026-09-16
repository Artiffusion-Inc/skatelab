import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { LandingClient } from "../landing-client"

vi.mock("next/image", () => ({
  default: (props: Record<string, unknown>) => <div data-testid="next-image" {...props} />,
}))

vi.mock("react-focus-lock", () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}))

describe("LandingClient school landing", () => {
  it("keeps the school pilot path and avoids consumer pricing copy", () => {
    render(<LandingClient />)

    expect(
      screen.getByRole("heading", { name: "Техника фигуриста. Данные для тренера." }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /Обсудить пилот/ }).length).toBeGreaterThan(0)
    expect(screen.getByRole("link", { name: "Посмотреть пример разбора" })).toHaveAttribute(
      "href",
      "#demo",
    )
    expect(screen.queryByText("Тарифы")).not.toBeInTheDocument()
    expect(screen.getByText("Иллюстрация будущего интерфейса")).toBeInTheDocument()
  })

  it("switches the clearly labelled example states with keyboard-capable tabs", () => {
    render(<LandingClient />)

    const dataTab = screen.getByRole("tab", { name: "Данные" })
    fireEvent.click(dataTab)

    expect(dataTab).toHaveAttribute("aria-selected", "true")
    expect(dataTab).toHaveAttribute("aria-controls", "demo-panel")
    expect(screen.getByRole("heading", { name: "Связанные показатели" })).toBeInTheDocument()
    expect(screen.getAllByText("Не является результатом измерения").length).toBeGreaterThan(0)

    fireEvent.keyDown(dataTab, { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: "Разбор" })).toHaveAttribute("aria-selected", "true")
  })
})
