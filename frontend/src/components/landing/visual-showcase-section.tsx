"use client"

import { useTranslations } from "@/i18n"
import { Film, LayoutDashboard, Box } from "lucide-react"

const icons = [Film, LayoutDashboard, Box]

export function VisualShowcaseSection() {
  const t = useTranslations("landing")

  const visuals = [
    { label: t("visualVideoLabel"), desc: t("visualVideoDesc") },
    { label: t("visualDashboardLabel"), desc: t("visualDashboardDesc") },
    { label: t("visual3dLabel"), desc: t("visual3dDesc") },
  ]

  return (
    <section
      id="visual"
      tabIndex={-1}
      aria-label={t("visualTitle")}
      className="relative mx-auto max-w-5xl px-6 py-16 md:py-24"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-caption text-ink-mute">{t("visualTitle")}</p>
        <h2 className="sh-display-xl text-ink max-w-xl">{t("visualHeadline")}</h2>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {visuals.map((v, i) => {
          const Icon = icons[i]
          const isWide = i === 0
          return (
            <div
              key={v.label}
              className={`visual-card group relative overflow-hidden rounded-lg border border-hairline bg-background ${
                isWide ? "md:col-span-2" : ""
              }`}
            >
              <div
                className={`bg-muted flex items-center justify-center ${
                  isWide ? "aspect-[21/9] md:items-end md:justify-start md:p-8" : "aspect-video"
                }`}
              >
                <div className={`text-center ${isWide ? "md:text-left" : ""}`}>
                  <Icon
                    className={`h-8 w-8 text-ink-mute mx-auto mb-2 ${isWide ? "md:mx-0" : ""}`}
                  />
                  <span className="sh-caption text-ink-mute">{v.label}</span>
                </div>
              </div>
              <div className="p-6">
                <h3 className="sh-heading-lg text-ink mb-1">{v.label}</h3>
                <p className="sh-caption text-ink-mute max-w-md">{v.desc}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
