import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useSearchParams } from "next/navigation"
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
  beforeEach(() => {
    window.history.replaceState(null, "", "/")
    vi.mocked(useSearchParams).mockImplementation(
      () => new URLSearchParams(window.location.search) as ReturnType<typeof useSearchParams>,
    )
  })
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

  it("explains the chosen phase in place instead of linking the figures to another page", () => {
    const { container, rerender } = renderLanding()
    const phase = screen.getByRole("button", { name: /02 Отталкивание/ })
    fireEvent.click(phase)
    rerender(
      <ConsentProvider>
        <LandingClient />
      </ConsentProvider>,
    )
    expect(phase).toHaveAttribute("aria-pressed", "true")
    expect(container.querySelector("#story .phase-description")).toHaveTextContent("Отталкивание")
    expect(container.querySelector("#story a svg.public-trace")).toBeNull()
    expect(screen.getByRole("link", { name: "Как устроен разбор: все этапы" })).toHaveAttribute(
      "href",
      "/how-it-works?phase=2#phases",
    )
  })

  it("keeps landing editorial headings free of terminal punctuation", () => {
    renderLanding()

    for (const heading of screen
      .getAllByRole("heading")
      .filter(heading => !heading.closest(".phase-description"))) {
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
