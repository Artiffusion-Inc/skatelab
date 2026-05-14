"use client"

import { Activity, Music, TrendingUp } from "lucide-react"
import { useTranslations } from "@/i18n"

const icons = [Activity, Music, TrendingUp]

export function FeaturesSection() {
  const t = useTranslations("landing")

  const features = [
    {
      title: t("feature1Title"),
      description: t("feature1Desc"),
      accent: t("feature1Accent"),
    },
    {
      title: t("feature2Title"),
      description: t("feature2Desc"),
      accent: t("feature2Accent"),
    },
    {
      title: t("feature3Title"),
      description: t("feature3Desc"),
      accent: t("feature3Accent"),
    },
  ]

  return (
    <section
      id="features"
      tabIndex={-1}
      aria-label={t("featuresTitle")}
      className="relative mx-auto max-w-5xl px-6 py-20 md:py-28"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-caption text-ink-mute">{t("featuresTitle")}</p>
        <h2 className="sh-display-xl text-ink max-w-[65ch]">{t("featuresHeadline")}</h2>
      </div>

      <div className="grid gap-8">
        {features.map((feature, i) => {
          const Icon = icons[i]
          return (
            <div
              key={feature.title}
              className="feature-card group rounded-lg border border-hairline bg-background p-8 lg:p-10"
            >
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                  <Icon className="h-6 w-6 text-primary group-hover:text-primary-foreground" />
                </div>
                <div className="flex-1">
                  <h3 className="sh-display-md mb-3 text-ink">{feature.title}</h3>
                  <p className="sh-body-md max-w-[65ch] text-ink-mute">{feature.description}</p>
                  <p className="mt-4 sh-caption text-primary">{feature.accent}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
