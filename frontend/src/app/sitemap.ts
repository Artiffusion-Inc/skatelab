import { headers } from "next/headers"
import type { MetadataRoute } from "next"
import { loader } from "fumadocs-core/source"
import { CONTENT_I18N, docsUrl, LOCALES } from "@/lib/docs-i18n"
import { buildSitemapEntries, selectSitemapCollection } from "@/lib/sitemap"
import { blog } from "@/lib/blog-source"
import { PUBLIC_ROUTES, blogUrl } from "@/lib/public-site"
import { docs as docsCollection } from "../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: CONTENT_I18N,
  url: docsUrl,
})

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const host = (await headers()).get("host")?.split(":")[0] ?? ""
  const collection = selectSitemapCollection(host)
  if (collection === "docs")
    return LOCALES.flatMap(locale => buildSitemapEntries(docs.getPages(locale), host, locale, true))
  const entries: MetadataRoute.Sitemap =
    collection === "blog"
      ? []
      : PUBLIC_ROUTES.filter(path => path !== "/blog").map(path => ({
          url: `https://skatelab.ru${path}`,
        }))
  for (const locale of LOCALES) {
    entries.push({
      url: `https://skatelab.ru${blogUrl(locale)}`,
      alternates: {
        languages: Object.fromEntries(
          LOCALES.map(language => [language, `https://skatelab.ru${blogUrl(language)}`]),
        ),
      },
    })
    for (const post of blog.getPages(locale))
      entries.push({
        url: `https://skatelab.ru${post.url}`,
        lastModified: post.data.date,
        alternates: {
          languages: Object.fromEntries(
            LOCALES.filter(language => blog.getPage(post.slugs, language)).map(language => [
              language,
              `https://skatelab.ru${blogUrl(language, post.slugs)}`,
            ]),
          ),
        },
      })
  }
  return entries
}
