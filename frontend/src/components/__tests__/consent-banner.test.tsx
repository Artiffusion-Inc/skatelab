import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConsentBanner } from "../consent-banner"
import { PublicShell } from "../landing/public-shell"

const mocks = vi.hoisted(() => ({ posthogKey: "", setConsent: vi.fn() }))
vi.mock("@/lib/env", () => mocks)
vi.mock("@/i18n", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "ru",
}))
vi.mock("@/i18n/actions", () => ({ setLocale: vi.fn() }))
vi.mock("next/navigation", () => ({ usePathname: () => "/" }))
vi.mock("../consent-provider", () => ({
  useConsent: () => ({ showBanner: true, setConsent: mocks.setConsent, openBanner: vi.fn() }),
}))

describe(ConsentBanner, () => {
  for (const available of [false, true]) {
    it(`${available ? "offers" : "omits"} consent controls when analytics is ${available ? "configured" : "absent"}`, () => {
      mocks.posthogKey = available ? "configured" : ""
      render(
        <>
          <PublicShell>
            <main>Website</main>
          </PublicShell>
          <ConsentBanner />
        </>,
      )

      expect(!!screen.queryByRole("dialog")).toBe(available)
      expect(!!screen.queryByRole("button", { name: "footerCookieSettings" })).toBe(available)
      expect(screen.getByRole("link", { name: "footerCookiePolicy" })).toHaveAttribute(
        "href",
        "/cookies",
      )
      expect(mocks.setConsent).not.toHaveBeenCalled()
      if (available) {
        fireEvent.click(screen.getByRole("button", { name: "cookieDecline" }))
        expect(mocks.setConsent).toHaveBeenCalledWith({
          essential: true,
          analytics: false,
          recordings: false,
        })
      }
    })
  }
})
