"use client"

import { useTranslations } from "@/i18n"

export function TrustSection() {
  const t = useTranslations("landing")

  const items = [
    { labelKey: "trustCoachesLabel", descKey: "trustCoachesDesc" },
    { labelKey: "trustClubsLabel", descKey: "trustClubsDesc" },
    { labelKey: "trustFederationLabel", descKey: "trustFederationDesc" },
  ]

  return (
    <section
      id="trust"
      tabIndex={-1}
      className="border-t border-hairline mx-auto max-w-5xl px-6 py-16 md:py-20"
      aria-labelledby="trust-heading"
    >
      <h2 id="trust-heading" className="sr-only">
        {t("trustTitle")}
      </h2>
      <div className="grid gap-8 sm:grid-cols-3">
        {items.map(item => (
          <div key={item.labelKey} className="text-center sm:text-left">
            <p className="sh-heading-lg text-primary">{t(item.labelKey)}</p>
            <p className="mt-2 sh-caption text-ink-mute">{t(item.descKey)}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
