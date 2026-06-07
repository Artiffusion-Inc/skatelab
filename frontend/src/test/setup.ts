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

// Mock @/i18n for components that use useTranslations
vi.mock("@/i18n", () => ({
  useTranslations: vi.fn((namespace: string) => {
    // Return a translation function that returns the key (identity) or interpolated string
    return vi.fn((key: string, params?: Record<string, string>) => {
      // Simple interpolation for common patterns
      if (params) {
        let result = key
        for (const [k, v] of Object.entries(params)) {
          result = result.replace(new RegExp(`{${k}}`, "g"), String(v))
        }
        return result
      }
      return key
    })
  }),
}))

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
