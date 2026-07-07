import type { ReactNode } from "react"
import Link from "next/link"
import { resolveLocale, LOCALES, type Locale } from "@/lib/docs-i18n"

// ponytail: blog has its own look (no DocsLayout) per plan Step 5. Header is
// just logo + locale switcher; all other chrome lives in the page.
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
    <div>
      <header className="flex items-center justify-between px-6 py-4 border-b">
        <Link href={`/${loc}`} className="font-semibold">
          SkateLab
        </Link>
        <nav className="flex gap-3 text-sm">
          {LOCALES.map(l => (
            <Link key={l} href={`/${l}`} hrefLang={l} className="uppercase">
              {l}
            </Link>
          ))}
        </nav>
      </header>
      {children}
    </div>
  )
}
