"use client"

import { useTranslations } from "@/i18n"
import { Film, LayoutDashboard, Box } from "lucide-react"

const icons = [Film, LayoutDashboard, Box]

export function VisualShowcaseSection() {
  const t = useTranslations("landing")

  const visuals = [
    {
      label: t("visualVideoLabel"),
      desc: t("visualVideoDesc"),
    },
    {
      label: t("visualDashboardLabel"),
      desc: t("visualDashboardDesc"),
    },
    {
      label: t("visual3dLabel"),
      desc: t("visual3dDesc"),
    },
  ]

  return (
    <section
      id="visual"
      tabIndex={-1}
      aria-label={t("visualTitle")}
      className="relative mx-auto max-w-5xl px-6 py-20 md:py-28"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("visualTitle")}
        </p>
        <h2 className="sh-display-xl text-ink">{t("visualHeadline")}</h2>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {visuals.map((v, i) => {
          const Icon = icons[i]
          return (
            <div
              key={i}
              className="visual-card group relative overflow-hidden rounded-lg border border-hairline bg-background"
            >
              <div className="aspect-video bg-ice-surface border-b border-hairline flex items-center justify-center">
                <div className="text-center">
                  <Icon className="h-8 w-8 text-ink-faint mx-auto mb-2" />
                  <span className="sh-caption text-ink-faint">{v.label}</span>
                </div>
              </div>
              <div className="p-6">
                <h3 className="sh-heading-lg text-ink mb-1">{v.label}</h3>
                <p className="sh-caption text-ink-mute">{v.desc}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
