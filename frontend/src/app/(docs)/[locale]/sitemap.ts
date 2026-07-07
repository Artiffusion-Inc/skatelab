import type { MetadataRoute } from "next"
import { loader } from "fumadocs-core/source"
import { LOCALES, DEFAULT_LOCALE } from "@/lib/docs-i18n"
// ponytail: see (docs)/[locale]/layout.tsx — relative import to generated
// .source/server (Fumadocs generates .source on dev/build, not at test time;
// no tsconfig/vitest alias for @/.source). Each sitemap duplicates the
// loader setup rather than reaching into another route file's private
// `docs` const — same pattern, two callers, no premature shared lib.
import { docs as docsCollection } from "../../../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = []
  for (const loc of LOCALES) {
    // ponytail: getPages returns one entry per (locale, page) — Fumadocs
    // i18n scopes content under the locale segment, so we iterate per-locale
    // for explicit alternates. Internal is staff-gated; exclude from public
    // sitemap so search engines don't discover /internal/* even via XML.
    for (const page of docs.getPages(loc)) {
      if (page.url.includes("/internal/")) continue
      entries.push({
        url: `https://docs.skatelab.ru/${loc}${page.url}`,
        alternates: {
          languages: Object.fromEntries(
            LOCALES.map(l => [l, `https://docs.skatelab.ru/${l}${page.url}`]),
          ),
        },
      })
    }
  }
  return entries
}
