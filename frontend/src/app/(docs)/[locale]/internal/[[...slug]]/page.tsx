import { notFound } from "next/navigation"
import { loader } from "fumadocs-core/source"
import { resolveLocale, LOCALES, DEFAULT_LOCALE, type Locale } from "@/lib/docs-i18n"
import { requireStaff } from "@/lib/staff"
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

// ponytail: force-dynamic so MDX does not leak as static (gate runs per request).
export const dynamic = "force-dynamic"

export default async function Page({
  params,
}: {
  params: Promise<{ locale: string; slug?: string[] }>
}) {
  const { locale, slug } = await params
  const loc: Locale = resolveLocale(locale)
  await requireStaff(`/${loc}/internal/${slug?.join("/") ?? ""}`)
  const page = docs.getPage(slug ? ["internal", ...slug] : ["internal"], loc)
  if (!page) notFound()
  const MDX = page.data.body
  return <MDX />
}
