import { getTranslations } from "next-intl/server"
import { PublicShell } from "@/components/landing/public-shell"

export default async function NotFound() {
  const t = await getTranslations("publicSite")
  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1} className="public-page-intro public-bio">
        <p className="public-eyebrow">404 / SkateLab</p>
        <h1>{t("missingTitle")}</h1>
        <p>{t("missingBody")}</p>
        <a href="/" className="public-text-link">
          {t("homeLink")} ↗
        </a>
      </main>
    </PublicShell>
  )
}
