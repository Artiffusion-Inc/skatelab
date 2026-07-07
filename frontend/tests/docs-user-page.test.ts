import { describe, it, expect } from "vitest"
import { resolveLocale, LOCALES, DEFAULT_LOCALE } from "../src/lib/docs-i18n"

// ponytail: plan's Task 4 test re-tests docs-i18n helpers (already covered in
// T003). Kept minimal per task brief — exercises locale resolution which the
// [locale] layout/page depend on. Importing the layout/page modules directly
// is blocked: they import `@/.source` which has no tsconfig/vitest alias
// (Fumadocs generates .source on dev/build, not at test time).
describe("docs user page locale", () => {
  it("resolves ru", () => {
    expect(resolveLocale("ru")).toBe("ru")
  })
  it("resolves en", () => {
    expect(resolveLocale("en")).toBe("en")
  })
  it("falls back to default ru for unknown", () => {
    expect(resolveLocale("xx")).toBe(DEFAULT_LOCALE)
    expect(resolveLocale(undefined)).toBe(DEFAULT_LOCALE)
  })
  it("LOCALES has ru+en", () => {
    expect(LOCALES).toEqual(["ru", "en"])
  })
})
