import type { MetadataRoute } from "next"
import { LOCALES } from "@/lib/docs-i18n"

export type SitemapCollection = "blog" | "docs"

type SitemapPage = { url: string }

export function selectSitemapCollection(host: string): SitemapCollection | null {
  if (host === "blog.skatelab.ru") return "blog"
  if (host === "docs.skatelab.ru") return "docs"
  return null
}

export function buildSitemapEntries(
  pages: readonly SitemapPage[],
  host: string,
  locale: string,
  excludeInternal = false,
): MetadataRoute.Sitemap {
  return pages
    .filter(page => !excludeInternal || !page.url.includes("/internal/"))
    .map(page => {
      const rawPath = page.url.startsWith("/") ? page.url : `/${page.url}`
      const path = rawPath.replace(/^\/(ru|en)(?=\/|$)/, "")
      return {
        url: `https://${host}/${locale}${path}`,
        alternates: {
          languages: Object.fromEntries(
            LOCALES.map(language => [language, `https://${host}/${language}${path}`]),
          ),
        },
      }
    })
}
