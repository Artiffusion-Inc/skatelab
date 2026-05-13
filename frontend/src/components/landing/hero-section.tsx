"use client"

import Image from "next/image"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

export function HeroSection() {
  const t = useTranslations("landing")

  const pills = [t("heroPill1"), t("heroPill2"), t("heroPill3")]

  return (
    <section
      className="hero-section relative flex min-h-[100dvh] items-center overflow-hidden"
      aria-label={t("eyebrow")}
    >
      <div className="sh-ice-backdrop absolute inset-0 z-0" aria-hidden="true" />

      <div className="absolute inset-0 z-0 hidden lg:block" aria-hidden="true">
        <Image
          src="/images/hero-skater.webp"
          alt=""
          fill
          className="object-cover object-center opacity-[0.08]"
          priority
        />
      </div>

      <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-16 sm:py-20 lg:py-24">
        <div className="max-w-2xl">
          <p className="hero-eyebrow mb-5 sh-caption text-ink-mute">
            {t("eyebrow")}
          </p>

          <h1 className="hero-headline sh-display-xxl text-ink">
            {t("headline")}
          </h1>

          <p className="hero-subtitle mt-5 max-w-[65ch] sh-body-lg text-ink-mute leading-relaxed">
            {t("subtitle")}
          </p>

          <div className="hero-pills mt-8 flex flex-wrap gap-2">
            {pills.map(pill => (
              <span
                key={pill}
                className="sh-badge-flat inline-flex items-center rounded-full px-3 py-1.5 sh-micro text-primary-foreground"
              >
                {pill}
              </span>
            ))}
          </div>

          <div className="hero-cta mt-10 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
            <Button
              variant="default"
              size="lg"
              className="min-h-[44px] h-14 px-10 text-base sh-button-cap"
              asChild
            >
              <a
                href="https://t.me/SkateLabPro"
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("ctaPrimary")}
              </a>
            </Button>
            <a
              href="/register"
              className="min-h-[44px] flex items-center sh-body-md text-link underline underline-offset-4 hover:text-primary-deep transition-colors"
            >
              {t("ctaSecondary")}
            </a>
          </div>
        </div>
      </div>

      <a
        href="#features"
        className="hero-scroll absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 group"
        aria-label={t("scrollToFeatures")}
      >
        <span className="sh-micro text-ink-mute tracking-widest uppercase opacity-0 group-hover:opacity-100 transition-opacity duration-300">
          {t("featuresTitle")}
        </span>
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          className="text-ink-mute group-hover:text-primary transition-colors duration-300"
        >
          <path
            d="M10 4v12m0 0l-4-4m4 4l4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </a>
    </section>
  )
}
