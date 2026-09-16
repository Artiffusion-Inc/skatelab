import { notFound } from "next/navigation"
import { loader } from "fumadocs-core/source"
import { toFumadocsSource } from "fumadocs-mdx/runtime/server"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
// ponytail: see (docs)/[locale]/layout.tsx — relative import to generated
// .source/server (Fumadocs generates .source on dev/build, not at test time;
// no tsconfig/vitest alias for @/.source). `create.doc()` returns entries
// with `info.path`; convert them with Fumadocs' `toFumadocsSource()` before
// passing the collection to the loader.
import { blog as blogPages } from "../../../../../.source/server"

const blog = loader({
  source: toFumadocsSource(blogPages, []),
  baseUrl: "/blog",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export const dynamicParams = true

export default async function Page({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>
}) {
  const { locale, slug } = await params
  const loc: Locale = resolveLocale(locale)
  // ponytail: getPage(slugs, language) — Fumadocs 16 API (validated in T004).
  // Cast to any at read-time: .source/server.ts is `@ts-nocheck`; per-page
  // data shape is what create.doc() spreads (body + frontmatter).
  const post = blog.getPage([slug], loc) as
    | (Awaited<ReturnType<typeof blog.getPage>> & {
        data: { body: React.ComponentType; date?: string }
      })
    | undefined
  if (!post) notFound()
  const MDX = post.data.body
  return (
    <article className="px-6 py-8">
      <MDX />
    </article>
  )
}
