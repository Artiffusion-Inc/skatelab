import { PublicShell } from "@/components/landing/public-shell"
import { TELEGRAM_URL } from "@/lib/public-site"
import { getTranslations } from "next-intl/server"

export default async function LegalLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("common")

  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1} className="public-legal mx-auto max-w-3xl px-6 py-8">
        {children}
        <aside className="mt-10 border-t pt-6 sh-body-md text-ink-mute" role="note">
          <strong className="block text-ink">{t("legalDraftLabel")}</strong>
          {t("legalDraftNotice")}
          <a className="block mt-3 underline" href={TELEGRAM_URL}>
            Telegram ↗
          </a>
        </aside>
      </main>
    </PublicShell>
  )
}
