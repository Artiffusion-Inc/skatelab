import { notFound } from "next/navigation"
import { loader } from "fumadocs-core/source"
import { CONTENT_I18N, docsUrl, isLocale } from "@/lib/docs-i18n"
import { requireStaff } from "@/lib/staff"
// ponytail: see layout.tsx — relative import to generated .source/server.
import { docs as docsCollection } from "../../../../../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: CONTENT_I18N,
  url: docsUrl,
})

// ponytail: force-dynamic so MDX does not leak as static (gate runs per request).
export const dynamic = "force-dynamic"

export default async function Page({
  params,
}: {
  params: Promise<{ locale: string; slug?: string[] }>
}) {
  const { locale, slug } = await params
  if (!isLocale(locale)) notFound()
  const loc = locale
  await requireStaff(`/${loc}/internal/${slug?.join("/") ?? ""}`)
  const page = docs.getPage(slug ? ["internal", ...slug] : ["internal"], loc)
  if (!page) notFound()
  const MDX = page.data.body
  return <MDX />
}
