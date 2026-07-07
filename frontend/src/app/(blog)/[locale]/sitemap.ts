import type { MetadataRoute } from "next"
import { loader, source } from "fumadocs-core/source"
import { LOCALES, DEFAULT_LOCALE } from "@/lib/docs-i18n"
// ponytail: see (blog)/[locale]/page.tsx — relative import to generated
// .source/server. `create.doc()` returns bare pages (no .toFumadocsSource()),
// so wrap with `source({ pages, metas })`. Each sitemap duplicates the
// loader setup — two callers, no premature shared lib.
import { blog as blogPages } from "../../../../.source/server"

const blog = loader({
  source: source({ pages: blogPages as never, metas: [] }),
  baseUrl: "/blog",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = []
  for (const loc of LOCALES) {
    for (const page of blog.getPages(loc)) {
      entries.push({
        url: `https://blog.skatelab.ru/${loc}${page.url}`,
        alternates: {
          languages: Object.fromEntries(
            LOCALES.map((l) => [l, `https://blog.skatelab.ru/${l}${page.url}`])
          ),
        },
      })
    }
  }
  return entries
}
