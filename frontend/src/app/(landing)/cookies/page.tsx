import type { Metadata } from "next"
import { getLocale, getTranslations } from "next-intl/server"
import { publicMetadata } from "@/lib/public-site"
import LegalLayout from "../legal-layout"

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("cookies")
  return publicMetadata(t("title"), t("intro"), "/cookies", await getLocale())
}

export default async function CookiesPage() {
  const t = await getTranslations("cookies")
  const tCommon = await getTranslations("common")
  const sections = [
    [t("s1"), t("p1")],
    [t("s2"), t("p2")],
    [t("s3"), t("p3")],
    [t("s4"), t("p4")],
    [t("s5"), t("p5")],
  ] as const

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
      <div className="space-y-6 sh-body-md text-ink-mute">
        <p className="sh-body-lg">{t("intro")}</p>
        {sections.map(([heading, body]) => (
          <section key={heading} className="space-y-2">
            <h2 className="sh-heading-lg text-ink">{heading}</h2>
            <p>{body}</p>
          </section>
        ))}
      </div>
    </LegalLayout>
  )
}
