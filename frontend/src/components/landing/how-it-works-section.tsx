"use client"

import { Bluetooth, Radio, BarChart3 } from "lucide-react"
import { useTranslations } from "@/i18n"

const icons = [Bluetooth, Radio, BarChart3]

function StepImage({
  src,
  alt = "",
  className,
}: {
  src: string
  alt?: string
  className?: string
}) {
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      aria-hidden="true"
      style={{ objectFit: "cover", width: "100%", height: "100%" }}
    />
  )
}

export function HowItWorksSection() {
  const t = useTranslations("landing")

  const steps = [
    {
      title: t("howItWorksStep1Title"),
      description: t("howItWorksStep1Desc"),
      accent: t("howItWorksStep1Accent"),
      img: "/images/moodboard/how-step1.webp",
      position: "object-center" as const,
    },
    {
      title: t("howItWorksStep2Title"),
      description: t("howItWorksStep2Desc"),
      accent: t("howItWorksStep2Accent"),
      img: "/images/moodboard/hero-mobile.webp",
      position: "object-center" as const,
    },
    {
      title: t("howItWorksStep3Title"),
      description: t("howItWorksStep3Desc"),
      accent: t("howItWorksStep3Accent"),
      img: "/images/moodboard/how-step3.webp",
      position: "object-left" as const,
    },
  ]

  const _FirstIcon = icons[0]

  return (
    <section
      id="how-it-works"
      tabIndex={-1}
      aria-label={t("howItWorksTitle")}
      className="relative mx-auto max-w-5xl px-6 py-24 md:py-32"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-caption text-ink-mute">{t("howItWorksTitle")}</p>
        <h2 className="sh-display-xl text-ink max-w-[65ch]">{t("howItWorksHeadline")}</h2>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        {steps.map((step, i) => {
          const Icon = icons[i]
          return (
            <div
              key={step.title}
              className="hiw-step group rounded-lg border border-hairline bg-background overflow-hidden"
            >
              <div className="relative aspect-[4/3]">
                <StepImage src={step.img} className="absolute inset-0 z-0" />
                <span className="step-watermark">0{i + 1}</span>
              </div>
              <div className="p-6">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                  <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
                </div>
                <h3 className="sh-heading-lg mb-2 text-ink">{step.title}</h3>
                <p className="sh-body-md text-ink-mute max-w-[65ch]">{step.description}</p>
                <p className="mt-3 sh-caption text-primary">{step.accent}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
