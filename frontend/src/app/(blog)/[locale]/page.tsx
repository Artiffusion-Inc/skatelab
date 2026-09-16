import Link from "next/link"
import { loader } from "fumadocs-core/source"
import { toFumadocsSource } from "fumadocs-mdx/runtime/server"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
// ponytail: see (docs)/[locale]/layout.tsx — relative import to generated
// .source/server (Fumadocs generates .source on dev/build, not at test time;
// no tsconfig/vitest alias for @/.source). `create.doc()` returns entries
// with `info.path`; convert them with Fumadocs' `toFumadocsSource()` before
// passing the collection to the loader.
import { blog as blogPages } from "../../../../.source/server"

const blog = loader({
  source: toFumadocsSource(blogPages, []),
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
