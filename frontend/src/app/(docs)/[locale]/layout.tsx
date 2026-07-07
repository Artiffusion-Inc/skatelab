import { DocsLayout } from "fumadocs-ui/layouts/docs"
import type { ReactNode } from "react"
import { loader } from "fumadocs-core/source"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
// ponytail: @/.source has no tsconfig/vitest alias (Fumadocs generates .source
// on dev/build, not test-time). Relative import to generated server entry.
// .source/server.ts is @ts-nocheck and uses top-level await — server-only.
import { docs as docsCollection } from "../../../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export default async function Layout({
  params,
  children,
}: {
  params: Promise<{ locale: string }>
  children: ReactNode
}) {
  const { locale } = await params
  const loc: Locale = resolveLocale(locale)
  return (
    <DocsLayout
      nav={{ title: "SkateLab" }}
      tree={docs.getPageTree(loc)}
    >
      {children}
    </DocsLayout>
  )
}