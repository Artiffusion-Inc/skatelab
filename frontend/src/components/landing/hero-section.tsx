"use client"

import Image from "next/image"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { SkeletonPose } from "./skeleton-pose"

export function HeroSection() {
  const t = useTranslations("landing")

  return (
    <section
      className="hero-section relative flex min-h-[100dvh] items-center overflow-hidden bg-primary"
      aria-label={t("eyebrow")}
    >
      {/* Violet-sky atmospheric backdrop */}
      <div className="sh-violet-backdrop absolute inset-0" />

      <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-16 sm:py-20 lg:py-24">
        <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
          {/* Left: text */}
          <div className="text-left">
            <p className="hero-eyebrow mb-5 sh-micro uppercase tracking-[0.3em] text-on-dark-mute">
              {t("eyebrow")}
            </p>

            <h1 className="hero-headline sh-display-xxl text-primary-foreground">
              {t("headline")}
              <br />
              <span className="text-surface-violet-soft">{t("headlineLine2")}</span>
            </h1>

            <p className="hero-subtitle mt-5 max-w-lg sh-body-lg text-on-dark-mute">
              {t("subtitle")}
            </p>

            {/* Coaching-outcome stat */}
            <div className="hero-cta mt-3 flex items-baseline gap-2">
              <span className="sh-display-lg text-surface-violet-soft">{t("heroStatValue")}</span>
              <span className="sh-caption text-on-dark-mute">{t("heroStatLabel")}</span>
            </div>

            <div className="hero-cta mt-8 flex flex-col items-start gap-4 sm:flex-row">
              <Button variant="on-dark-pill" size="lg" className="h-14 px-10 text-base" asChild>
                <a href="/register">{t("ctaPrimary")}</a>
              </Button>
              <Button
                variant="ghost"
                size="lg"
                className="h-14 rounded-full px-8 text-base text-on-dark-mute hover:text-primary-foreground"
                asChild
              >
                <a href="#demo">{t("ctaSecondary")}</a>
              </Button>
            </div>
          </div>

          {/* Right: skating image with skeleton overlay */}
          <div className="hero-image relative">
            <div className="relative aspect-[16/9] overflow-hidden rounded-lg lg:aspect-[4/5]">
              <Image
                src="/images/hero-skater.webp"
                alt="Figure skater performing a jump on ice"
                fill
                sizes="(max-width: 1024px) 100vw, 52vw"
                className="object-cover"
                priority
              />
              <div className="absolute inset-0 bg-primary/40" />
              <SkeletonPose role="img" aria-label="AI отслеживает 17 ключевых точек тела" />
              {/* Inline metric badge */}
              <div className="sh-badge-opaque absolute top-[15%] right-[8%] rounded-md px-4 py-3">
                <p className="sh-micro uppercase tracking-wider text-on-dark-dim">
                  {t("heroOverlayLabel")}
                </p>
                <p className="sh-caption text-primary-foreground">{t("heroOverlayValue")}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Gradient bridge to next section */}
      <div
        className="h-20 md:h-28 bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent"
        aria-hidden="true"
      />

      <div className="hero-scroll absolute bottom-8 left-1/2 -translate-x-1/2" aria-hidden="true">
        <svg
          role="img"
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M10 4v12m0 0l-4-4m4 4l4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-on-dark-mute"
          />
        </svg>
      </div>
    </section>
  )
}
