import { describe, expect, it } from "vitest"
import { buildSitemapEntries, selectSitemapCollection } from "@/lib/sitemap"

describe("host-aware content sitemaps", () => {
  it("keeps blog and docs entries on their intended hosts", () => {
    const pages = [{ url: "/en/user/getting-started" }, { url: "/en/internal/architecture" }]

    expect(buildSitemapEntries(pages, "docs.skatelab.ru", "en", true)).toEqual([
      {
        url: "https://docs.skatelab.ru/en/user/getting-started",
        alternates: {
          languages: {
            en: "https://docs.skatelab.ru/en/user/getting-started",
            ru: "https://docs.skatelab.ru/ru/user/getting-started",
          },
        },
      },
    ])
    expect(selectSitemapCollection("blog.skatelab.ru")).toBe("blog")
    expect(selectSitemapCollection("docs.skatelab.ru")).toBe("docs")
    expect(selectSitemapCollection("skatelab.ru")).toBeNull()
  })
})
