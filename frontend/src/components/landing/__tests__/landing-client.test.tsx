import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConsentProvider } from "@/components/consent-provider"
import { LandingClient } from "../landing-client"

vi.mock("next/image", () => ({
  default: (props: Record<string, unknown>) => <div data-testid="next-image" {...props} />,
}))

vi.mock("react-focus-lock", () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}))

function renderLanding() {
  return render(
    <ConsentProvider>
      <LandingClient />
    </ConsentProvider>,
  )
}

describe("LandingClient campaign", () => {
  it("presents a mobile-first school pilot path without web-account access", () => {
    renderLanding()

    expect(
      screen.getByRole("heading", { name: "Каждая попытка Понятнее тренеру" }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /Обсудить пилот/ }).length).toBeGreaterThan(0)
    expect(screen.queryByRole("link", { name: "Войти" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("link").some(link => link.getAttribute("href") === "/login")).toBe(
      false,
    )
    expect(
      screen
        .getAllByRole("link")
        .filter(link => link.getAttribute("href") === "https://t.me/xpos587").length,
    ).toBeGreaterThan(2)
    expect(
      screen.queryByText(/Приложение в разработке|Сценарий проверяется|будет добавлена/),
    ).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Конфиденциальность" })).toHaveAttribute(
      "href",
      "/privacy",
    )
    expect(screen.queryByText(/Синтетическое изображение/)).not.toBeInTheDocument()
    expect(screen.queryByText("Тарифы")).not.toBeInTheDocument()
  })

  it("keeps landing headings free of terminal punctuation", () => {
    renderLanding()

    for (const heading of screen.getAllByRole("heading")) {
      expect(heading.textContent).not.toMatch(/[.!?]$/)
    }
  })

  it("connects the homepage to complete public destinations", () => {
    renderLanding()
    for (const href of ["/how-it-works", "/equipment", "/blog/ru", "/contact"]) {
      expect(screen.getAllByRole("link").some(link => link.getAttribute("href") === href)).toBe(
        true,
      )
    }
  })
})
