import { notFound } from "next/navigation"
import { RootProvider } from "fumadocs-ui/provider/next"
import { DocsLayout } from "fumadocs-ui/layouts/docs"
import type { ReactNode } from "react"
import { loader } from "fumadocs-core/source"
import { CONTENT_I18N, docsUrl, isLocale } from "@/lib/docs-i18n"
// ponytail: @/.source has no tsconfig/vitest alias (Fumadocs generates .source
// on dev/build, not test-time). Relative import to generated server entry.
// .source/server.ts is @ts-nocheck and uses top-level await — server-only.
import { docs as docsCollection } from "../../../../.source/server"

const docs = loader({
  source: docsCollection.toFumadocsSource(),
  baseUrl: "/docs",
  i18n: CONTENT_I18N,
  url: docsUrl,
})

export default async function Layout({
  params,
  children,
}: {
  params: Promise<{ locale: string }>
  children: ReactNode
}) {
  const { locale } = await params
  if (!isLocale(locale)) notFound()
  const loc = locale
  return (
    <RootProvider search={{ enabled: false }} theme={{ enabled: false }}>
      <DocsLayout nav={{ title: "SkateLab" }} tree={docs.getPageTree(loc)}>
        {children}
      </DocsLayout>
    </RootProvider>
  )
}
