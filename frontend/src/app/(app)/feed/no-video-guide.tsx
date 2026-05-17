"use client"

import { useTranslations } from "@/i18n"
import { Camera, Sun, Film } from "lucide-react"

export function NoVideoGuide() {
  const t = useTranslations("feed")

  const tips = [
    { icon: Camera, title: t("guideAngleTitle"), desc: t("guideAngleDesc") },
    { icon: Sun, title: t("guideLightTitle"), desc: t("guideLightDesc") },
    { icon: Film, title: t("guideFormatTitle"), desc: t("guideFormatDesc") },
  ]

  return (
    <div className="space-y-3 rounded-2xl border border-hairline p-4">
      <h3 className="text-sm font-medium">{t("guideTitle")}</h3>
      {tips.map(tip => {
        const Icon = tip.icon
        return (
          <div key={tip.title} className="flex gap-3">
            <Icon className="h-5 w-5 shrink-0 text-primary" />
            <div>
              <p className="text-sm font-medium">{tip.title}</p>
              <p className="text-xs text-ink-mute">{tip.desc}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
