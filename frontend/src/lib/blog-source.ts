import { loader } from "fumadocs-core/source"
import { toFumadocsSource } from "fumadocs-mdx/runtime/server"
import { blog as blogPages } from "../../.source/server"
import { CONTENT_I18N, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
import { blogUrl } from "@/lib/public-site"

export const blog = loader({
  source: toFumadocsSource(blogPages, []),
  baseUrl: "/blog",
  i18n: CONTENT_I18N,
  url: (slugs, locale) => blogUrl((locale ?? DEFAULT_LOCALE) as Locale, slugs),
})

export function getBlogPosts(locale: Locale) {
  return blog
    .getPages(locale)
    .sort(
      (a, b) =>
        b.data.date.localeCompare(a.data.date) ||
        a.slugs.join("/").localeCompare(b.slugs.join("/")),
    )
}
