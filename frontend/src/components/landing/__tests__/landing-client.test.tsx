import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { LandingClient } from "../landing-client"

vi.mock("next/image", () => ({
  default: (props: Record<string, unknown>) => <div data-testid="next-image" {...props} />,
}))

vi.mock("react-focus-lock", () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}))

describe("LandingClient campaign", () => {
  it("presents a truthful school pilot path with working app and legal links", () => {
    render(<LandingClient />)

    expect(
      screen.getByRole("heading", { name: "Тренер видит то, что теряется между попытками." }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /Обсудить пилот/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole("link", { name: "Войти" })[0]).toHaveAttribute("href", "/login")
    expect(screen.getByRole("link", { name: "Конфиденциальность" })).toHaveAttribute(
      "href",
      "/privacy",
    )
    expect(screen.getByText("Синтетическое изображение · не кадр продукта")).toBeInTheDocument()
    expect(screen.queryByText("Тарифы")).not.toBeInTheDocument()
  })

  it("switches the working-loop story with accessible tabs", () => {
    render(<LandingClient />)

    const connectTab = screen.getByRole("tab", { name: /Сопоставить/ })
    fireEvent.click(connectTab)

    expect(connectTab).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "story-tab-sense")
    expect(screen.getByRole("heading", { name: "Сопоставить движение" })).toBeInTheDocument()

    fireEvent.keyDown(connectTab, { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: /Решить/ })).toHaveAttribute("aria-selected", "true")
  })
})
