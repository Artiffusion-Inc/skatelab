import { describe, it, expect } from "vitest"
import { resolveLocale, DEFAULT_LOCALE, LOCALES } from "../src/lib/docs-i18n"

// ponytail: same rationale as docs-user-page.test.ts — page/layout modules
// import `@/.source` (no tsconfig/vitest alias, Fumadocs generates .source
// on dev/build, not at test time). Test the locale helpers the blog depends
// on; leave module-shape assertions to T002 source-config.test.ts.
describe("blog locale helpers", () => {
  it("ru resolves", () => {
    expect(resolveLocale("ru")).toBe("ru")
  })
  it("en resolves", () => {
    expect(resolveLocale("en")).toBe("en")
  })
  it("falls back to default for unknown / missing", () => {
    expect(resolveLocale("xx")).toBe(DEFAULT_LOCALE)
    expect(resolveLocale(undefined)).toBe(DEFAULT_LOCALE)
  })
  it("LOCALES has ru+en", () => {
    expect(LOCALES).toEqual(["ru", "en"])
  })
})
