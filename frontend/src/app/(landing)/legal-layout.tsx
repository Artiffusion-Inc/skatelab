import Link from "next/link"
import { getTranslations } from "next-intl/server"

export default async function LegalLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("common")

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-hairline px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <Link href="/" className="sh-display-md text-ink">
            SkateLab
          </Link>
          <Link href="/" className="sh-caption text-link hover:underline">
            {t("home")}
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">{children}</main>
    </div>
  )
}
