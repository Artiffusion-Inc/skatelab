import { afterEach, vi } from "vitest"

// Mock next/navigation for Next.js App Router hooks
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  })),
  useSearchParams: vi.fn(() => new URLSearchParams()),
  usePathname: vi.fn(() => "/"),
}))

// Mock @/i18n for components that use useTranslations / useLocale. Returns REAL
// ru strings from messages/ru.json (with {placeholder} interpolation) instead
// of bare key paths, so i18n-asserting tests check the actual user-facing text.
// Use the real next-intl NextIntlClientProvider instead of this mock only if a
// test needs ICU message-format features beyond simple {name} interpolation.
vi.mock("@/i18n", async () => {
  const messages = (await import("./../../messages/ru.json")).default as Record<
    string,
    Record<string, string>
  >
  const interpolate = (template: string, params?: Record<string, unknown>) => {
    if (!params) return template
    return template.replace(/\{(\w+)\}/g, (_m, k: string) =>
      k in params ? String(params[k]) : `{${k}}`,
    )
  }
  return {
    useLocale: () => "ru",
    useTranslations: (namespace: string) => (key: string, params?: Record<string, unknown>) => {
      const template = messages[namespace]?.[key]
      return template === undefined ? key : interpolate(template, params)
    },
  }
})

// Mock @sentry/nextjs (optional dep, may not be installed in CI)
vi.mock("@sentry/nextjs", () => ({
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  withScope: vi.fn((_, fn) => fn({ setExtra: vi.fn(), setTag: vi.fn() })),
  init: vi.fn(),
}))

import "@testing-library/jest-dom"
import { cleanup } from "@testing-library/react"
import { setupMSW } from "./server"

// Setup MSW for API mocking
setupMSW()

// Cleanup after each test
afterEach(() => {
  cleanup()
})

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})
