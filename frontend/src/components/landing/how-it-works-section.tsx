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

  const FirstIcon = icons[0]

  return (
    <section
      id="how-it-works"
      tabIndex={-1}
      aria-label={t("howItWorksTitle")}
      className="relative mx-auto max-w-5xl px-6 py-24 md:py-32"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-caption text-ink-mute">{t("howItWorksTitle")}</p>
        <h2 className="sh-display-xl text-ink max-w-xl">{t("howItWorksHeadline")}</h2>
      </div>

      {/* Step 1 — full-width card with image */}
      <div className="hiw-step group relative mb-8 overflow-hidden rounded-lg border border-hairline bg-background">
        <StepImage src={steps[0].img} className="absolute inset-0 z-0" />
        <div
          className="absolute inset-0 z-0"
          style={{
            background:
              "linear-gradient(to right, oklch(1 0 0 / 0.94) 0%, oklch(1 0 0 / 0.88) 45%, oklch(1 0 0 / 0.55) 100%)",
          }}
        />
        <div className="relative z-10 flex flex-col gap-6 p-8 lg:flex-row lg:items-start lg:gap-10 lg:p-12">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
            <FirstIcon className="h-6 w-6 text-primary group-hover:text-primary-foreground" />
          </div>
          <div>
            <h3 className="sh-display-md mb-3 text-ink">{steps[0].title}</h3>
            <p className="sh-body-md max-w-[65ch] text-ink-mute">{steps[0].description}</p>
            <p className="mt-4 sh-caption text-primary">{steps[0].accent}</p>
          </div>
        </div>
        <span className="step-watermark">01</span>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        {/* Step 2 — image card */}
        <div className="hiw-step group relative overflow-hidden rounded-lg border border-hairline bg-background">
          <StepImage src={steps[1].img} className="absolute inset-0 z-0" />
          <div
            className="absolute inset-0 z-0"
            style={{
              background:
                "linear-gradient(to bottom, oklch(1 0 0 / 0.92) 0%, oklch(1 0 0 / 0.82) 50%, oklch(1 0 0 / 0.6) 100%)",
            }}
          />
          <div className="relative z-10 p-8">
            <span className="step-watermark">02</span>
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
              {(() => {
                const Icon = icons[1]
                return <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
              })()}
            </div>
            <h3 className="sh-heading-lg mb-2 text-ink">{steps[1].title}</h3>
            <p className="sh-caption text-ink-mute max-w-[65ch]">{steps[1].description}</p>
            <p className="mt-3 sh-caption text-primary">{steps[1].accent}</p>
          </div>
        </div>

        {/* Step 3 — image card */}
        <div className="hiw-step group relative overflow-hidden rounded-lg border border-hairline bg-background">
          <StepImage src={steps[2].img} className="absolute inset-0 z-0" />
          <div
            className="absolute inset-0 z-0"
            style={{
              background:
                "linear-gradient(to bottom, oklch(1 0 0 / 0.92) 0%, oklch(1 0 0 / 0.82) 50%, oklch(1 0 0 / 0.6) 100%)",
            }}
          />
          <div className="relative z-10 flex flex-col justify-center p-8 h-full">
            <span className="step-watermark">03</span>
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-md bg-muted transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
              {(() => {
                const Icon = icons[2]
                return <Icon className="h-5 w-5 text-primary group-hover:text-primary-foreground" />
              })()}
            </div>
            <h3 className="sh-heading-lg mb-2 text-ink">{steps[2].title}</h3>
            <p className="sh-body-md text-ink-mute max-w-[65ch]">{steps[2].description}</p>
            <p className="mt-4 sh-caption text-primary">{steps[2].accent}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
