import { fireEvent, render, screen } from "@testing-library/react"
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
    expect(screen.getAllByText(/iPhone, iPad и Android/).length).toBeGreaterThan(0)
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

  it("switches the working-loop story with accessible tabs", () => {
    renderLanding()

    const connectTab = screen.getByRole("tab", { name: /Сопоставить/ })
    fireEvent.click(connectTab)

    expect(connectTab).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "story-tab-sense")
    expect(screen.getByRole("heading", { name: "Сопоставить движение" })).toBeInTheDocument()

    fireEvent.keyDown(connectTab, { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: /Решить/ })).toHaveAttribute("aria-selected", "true")
  })
})
