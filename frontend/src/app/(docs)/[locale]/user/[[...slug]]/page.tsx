import { notFound } from "next/navigation"
import { loader } from "fumadocs-core/source"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
// ponytail: see layout.tsx — relative import to generated .source/server.
import { docs as docsCollection } from "../../../../../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: {
    languages: LOCALES as unknown as string[],
    defaultLanguage: DEFAULT_LOCALE,
  },
})

export const dynamicParams = true

export default async function Page({
  params,
}: {
  params: Promise<{ locale: string; slug?: string[] }>
}) {
  const { locale, slug } = await params
  const loc: Locale = resolveLocale(locale)
  // Fumadocs 16: getPage(slugs, language). slug=["user", ...rest] maps to
  // content/docs/<locale>/user/<rest>. Pages are auto-scoped by locale.
  const page = docs.getPage(slug ? ["user", ...slug] : ["user"], loc)
  if (!page) notFound()
  const MDX = page.data.body
  return <MDX />
}
