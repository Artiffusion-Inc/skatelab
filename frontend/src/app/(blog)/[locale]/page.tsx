import Link from "next/link"
import { loader, source } from "fumadocs-core/source"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
// ponytail: see (docs)/[locale]/layout.tsx — relative import to generated
// .source/server (Fumadocs generates .source on dev/build, not at test time;
// no tsconfig/vitest alias for @/.source). `create.doc()` returns a bare
// array of pages (no `.toFumadocsSource()` like `create.docs()` does), so
// wrap with the `source({ pages, metas })` helper for non-docs collections.
import { blog as blogPages } from "../../../../.source/server"

const blog = loader({
  source: source({ pages: blogPages as never, metas: [] }),
  baseUrl: "/blog",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

// ponytail: per-page data shape from create.doc() spread (body + frontmatter).
// .source/server.ts is `@ts-nocheck`; cast at the boundary.
type BlogPageView = Awaited<ReturnType<typeof blog.getPages>>[number] & {
  data: { title?: string; date?: string }
}

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  const loc: Locale = resolveLocale(locale)
  // ponytail: date in frontmatter is YYYY-MM-DD; lexicographic sort = chrono.
  const posts = blog.getPages(loc) as unknown as BlogPageView[]
  posts.sort((a, b) => String(b.data.date ?? "").localeCompare(String(a.data.date ?? "")))
  return (
    <main className="px-6 py-8">
      <ul className="space-y-3">
        {posts.map(p => (
          <li key={p.url}>
            <Link href={p.url} className="underline">
              {p.data.title}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  )
}
