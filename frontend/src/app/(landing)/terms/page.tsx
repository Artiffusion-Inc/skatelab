import type { Metadata } from "next"
import Link from "next/link"
import { getTranslations } from "next-intl/server"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Пользовательское соглашение — SkateLab",
}

export default async function TermsPage() {
  const t = await getTranslations("terms")
  const tCommon = await getTranslations("common")

  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">
          {tCommon("home")}
        </a>
        {" > "}
        <span>{tCommon("legalInfo")}</span>
        {" > "}
        <span>{t("title")}</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">{t("title")}</h1>
      <p className="sh-body-lg text-ink-mute">{t("comingSoon")}</p>
      <p className="mt-4">
        <Link href="/" className="sh-button-cap text-link hover:underline">
          {tCommon("home")} →
        </Link>
      </p>
    </LegalLayout>
  )
}
