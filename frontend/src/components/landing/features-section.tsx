"use client"

import { Video, BarChart3, GitCompareArrows } from "lucide-react"
import { useTranslations } from "@/i18n"

const icons = [Video, BarChart3, GitCompareArrows]

export function HowItWorksSection() {
  const t = useTranslations("landing")

  const steps = [
    {
      title: t("howItWorksStep1Title"),
      description: t("howItWorksStep1Desc"),
      accent: t("howItWorksStep1Accent"),
    },
    {
      title: t("howItWorksStep2Title"),
      description: t("howItWorksStep2Desc"),
      accent: t("howItWorksStep2Accent"),
    },
    {
      title: t("howItWorksStep3Title"),
      description: t("howItWorksStep3Desc"),
      accent: t("howItWorksStep3Accent"),
    },
  ]

  const FirstIcon = icons[0]

  return (
    <section
      id="how-it-works"
      tabIndex={-1}
      aria-label={t("howItWorksTitle")}
      className="relative mx-auto max-w-5xl px-6 py-20 md:py-28"
    >
      {/* Section opener — left-aligned, asymmetric */}
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("howItWorksTitle")}
        </p>
        <h2 className="sh-display-xl text-ink max-w-xl">{t("howItWorksHeadline")}</h2>
      </div>

      {/* Step 1: full-width, dominant */}
      <div className="hiw-step group relative mb-8 overflow-hidden rounded-lg border border-hairline bg-background p-8 lg:p-12">
        <span className="step-watermark">01</span>
        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            <FirstIcon className="h-6 w-6 text-primary group-hover:text-primary-foreground" />
          </div>
          <div>
            <h3 className="sh-display-md mb-3 text-ink">{steps[0].title}</h3>
            <p className="sh-body-md max-w-lg text-ink-mute">{steps[0].description}</p>
            <p className="mt-4 sh-caption text-primary">{steps[0].accent}</p>
          </div>
        </div>
      </div>

      {/* Steps 2 & 3: paired row, varied proportions */}
      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        {/* Step 2: icon-left */}
        <div className="hiw-step group relative overflow-hidden rounded-lg border border-hairline bg-background p-8">
          <span className="step-watermark">02</span>
          <div className="relative z-10">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
              {(() => {
                const Icon = icons[1]
                return <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
              })()}
            </div>
            <h3 className="sh-heading-lg mb-2 text-ink">{steps[1].title}</h3>
            <p className="sh-caption text-ink-mute">{steps[1].description}</p>
            <p className="mt-3 sh-caption text-primary">{steps[1].accent}</p>
          </div>
        </div>

        {/* Step 3: narrative block, no icon box */}
        <div className="hiw-step group relative overflow-hidden rounded-lg border border-hairline bg-background p-8 flex flex-col justify-center">
          <span className="step-watermark">03</span>
          <div className="relative z-10">
            <h3 className="sh-heading-lg mb-2 text-ink">{steps[2].title}</h3>
            <p className="sh-body-md text-ink-mute">{steps[2].description}</p>
            <p className="mt-4 sh-caption text-primary">{steps[2].accent}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
