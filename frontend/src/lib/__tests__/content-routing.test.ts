import { loader } from "fumadocs-core/source"
import { describe, expect, it } from "vitest"
import { CONTENT_I18N, docsUrl, isLocale } from "@/lib/docs-i18n"
import { blogUrl } from "@/lib/public-site"

const files = [
  { type: "page" as const, path: "ru/recording-guide.mdx", data: { title: "Съёмка" } },
  { type: "page" as const, path: "en/recording-guide.mdx", data: { title: "Recording" } },
]
describe("directory-based Fumadocs routing", () => {
  it("keeps each locale collection isolated and generates served blog URLs", () => {
    const source = loader({
      source: { files },
      baseUrl: "/blog",
      i18n: CONTENT_I18N,
      url: (slugs, locale) => blogUrl(isLocale(locale) ? locale : "ru", slugs),
    })
    expect(source.getPages("ru")).toHaveLength(1)
    expect(source.getPage(["recording-guide"], "en")?.data.title).toBe("Recording")
    expect(source.getPage(["recording-guide"], "ru")?.url).toBe("/blog/ru/recording-guide")
    expect(source.getPage(["missing"], "en")).toBeUndefined()
    expect(isLocale("xx")).toBe(false)
  })
  it("uses existing docs URLs without a duplicate locale or phantom docs segment", () => {
    const source = loader({
      source: {
        files: files.map(file => ({
          ...file,
          path: file.path.replace("recording-guide", "user/getting-started"),
        })),
      },
      baseUrl: "/docs",
      i18n: CONTENT_I18N,
      url: docsUrl,
    })
    expect(source.getPage(["user", "getting-started"], "en")?.url).toBe("/en/user/getting-started")
    expect(source.getPage(["user", "getting-started"], "ru")?.data.title).toBe("Съёмка")
  })
})
