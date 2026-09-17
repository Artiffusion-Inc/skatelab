import { getLocale, getTranslations } from "next-intl/server"
import { PublicShell, ContactLink } from "@/components/landing/public-shell"
import { publicMetadata } from "@/lib/public-site"

export async function generateMetadata() {
  const t = await getTranslations("publicSite")
  return publicMetadata(t("bioTitle"), t("bioIntro"), "/tiktok", await getLocale())
}

export default async function TikTokPage() {
  const t = await getTranslations("publicSite")
  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1} className="public-page-intro public-bio">
        <p className="public-eyebrow">SkateLab</p>
        <h1>{t("bioTitle")}</h1>
        <p>{t("bioIntro")}</p>
        <nav aria-label={t("navProcess")}>
          <a href="/how-it-works" className="public-text-link">
            {t("navProcess")} ↗
          </a>
          <a href="/equipment" className="public-text-link">
            {t("navEquipment")} ↗
          </a>
          <a href="/blog" className="public-text-link">
            {t("navBlog")} ↗
          </a>
          <a href="/contact" className="public-text-link">
            {t("navContact")} ↗
          </a>
          <ContactLink />
        </nav>
      </main>
    </PublicShell>
  )
}
