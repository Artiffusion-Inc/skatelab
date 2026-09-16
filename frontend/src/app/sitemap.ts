import { headers } from "next/headers"
import type { MetadataRoute } from "next"
import { loader } from "fumadocs-core/source"
import { toFumadocsSource } from "fumadocs-mdx/runtime/server"
import { LOCALES, DEFAULT_LOCALE } from "@/lib/docs-i18n"
import { buildSitemapEntries, selectSitemapCollection } from "@/lib/sitemap"
import { blog as blogPages, docs as docsCollection } from "../../.source/server"

const blog = loader({
  source: toFumadocsSource(blogPages, []),
  baseUrl: "/blog",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const host = (await headers()).get("host")?.split(":")[0] ?? ""
  const collection = selectSitemapCollection(host)
  if (!collection) return []

  const entries: MetadataRoute.Sitemap = []
  for (const locale of LOCALES) {
    const pages = collection === "blog" ? blog.getPages(locale) : docs.getPages(locale)
    entries.push(...buildSitemapEntries(pages, host, locale, collection === "docs"))
  }
  return entries
}
