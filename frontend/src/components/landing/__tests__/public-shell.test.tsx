import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConsentProvider } from "@/components/consent-provider"
import { PublicShell } from "../public-shell"

vi.mock("@/i18n", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string) => key,
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/blog/en/recording-guide",
  useSearchParams: () => new URLSearchParams(),
}))

describe(PublicShell, () => {
  it("keeps journal navigation in the article language without a locale cookie", () => {
    render(
      <ConsentProvider>
        <PublicShell>
          <main>Article</main>
        </PublicShell>
      </ConsentProvider>,
    )

    expect(screen.getByRole("link", { name: "backHome" })).toHaveAttribute("href", "/#journal")

    for (const link of screen.getAllByRole("link", { name: "navBlog" })) {
      expect(link).toHaveAttribute("href", "/blog/en")
      expect(link).toHaveAttribute("aria-current", "page")
    }
  })
})
