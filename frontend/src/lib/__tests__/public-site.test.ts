import { describe, expect, it } from "vitest"
import { isPublicPage } from "@/lib/is-public-page"
import { blogUrl, TELEGRAM_URL } from "@/lib/public-site"

describe("public campaign routes", () => {
  it("keeps brand, editorial and link-in-bio traffic out of auth", () => {
    for (const path of [
      "/",
      "/how-it-works",
      "/equipment",
      "/contact",
      "/blog",
      "/blog/en/recording-guide",
      "/tiktok",
      "/privacy",
    ]) {
      expect(isPublicPage(path), path).toBe(true)
    }
    for (const path of [
      "/equipment-private",
      "/blogger",
      "/sessions/1",
      "/profile",
      "/privacy-settings",
    ]) {
      expect(isPublicPage(path), path).toBe(false)
    }
  })
  it("uses one confirmed contact and explicit bilingual article paths", () => {
    expect(TELEGRAM_URL).toBe("https://t.me/xpos587")
    expect(blogUrl("en", ["recording-guide"])).toBe("/blog/en/recording-guide")
    expect(blogUrl("ru")).toBe("/blog/ru")
  })
})
