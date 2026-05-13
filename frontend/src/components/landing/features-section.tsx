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
        <h2 className="sh-display-xl text-ink max-w-xl">{t("featuresHeadline")}</h2>
      </div>

      <div className="feature-card group relative mb-8 overflow-hidden rounded-lg border border-hairline bg-background p-8 lg:p-12">
        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            {(() => {
              const Icon = icons[0]
              return <Icon className="h-6 w-6 text-primary group-hover:text-primary-foreground" />
            })()}
          </div>
          <div className="flex-1">
            <h3 className="sh-display-md mb-3 text-ink">{features[0].title}</h3>
            <p className="sh-body-md max-w-[65ch] text-ink-mute">{features[0].description}</p>
            <p className="mt-4 sh-caption text-primary">{features[0].accent}</p>
          </div>
          <div className="hidden lg:block w-72 h-48 rounded-md bg-muted flex items-center justify-center">
            <span className="sh-caption text-ink-mute">{t("visualVideoLabel")}</span>
          </div>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
        <div className="feature-card group relative overflow-hidden rounded-lg border border-hairline bg-background p-8">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            {(() => {
              const Icon = icons[1]
              return <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
            })()}
          </div>
          <h3 className="sh-heading-lg mb-2 text-ink">{features[1].title}</h3>
          <p className="sh-caption text-ink-mute max-w-md">{features[1].description}</p>
          <p className="mt-3 sh-caption text-primary">{features[1].accent}</p>
        </div>

        <div className="feature-card group relative overflow-hidden rounded-lg border border-hairline bg-background p-8 flex flex-col justify-center">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            {(() => {
              const Icon = icons[2]
              return <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
            })()}
          </div>
          <h3 className="sh-heading-lg mb-2 text-ink">{features[2].title}</h3>
          <p className="sh-body-md text-ink-mute max-w-md">{features[2].description}</p>
          <p className="mt-4 sh-caption text-primary">{features[2].accent}</p>
        </div>
      </div>
    </section>
  )
}
