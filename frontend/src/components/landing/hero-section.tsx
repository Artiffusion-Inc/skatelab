"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

const GlyphDitherCanvas = dynamic(
  () => import("./hero-glyph-dither").then(m => m.GlyphDitherCanvas),
  { ssr: false },
)

export function HeroSection() {
  const t = useTranslations("landing")
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    setReducedMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  }, [])

  return (
    <section
      className="hero-section relative flex min-h-[100dvh] items-center overflow-hidden bg-primary"
      aria-label={t("eyebrow")}
    >
      {/* Midnight blue backdrop with WebGL glyph dither */}
      {!reducedMotion && (
        <div className="absolute inset-0 z-0">
          <GlyphDitherCanvas
            imageUrl="/images/hero-skater.webp"
            className="h-full w-full"
            opacity={0.85}
          />
        </div>
      )}

      {/* Reduced motion fallback */}
      {reducedMotion && <div className="sh-violet-backdrop absolute inset-0" />}

      {/* Text content */}
      <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-16 sm:py-20 lg:py-24">
        <div className="max-w-xl">
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

          <div className="hero-cta mt-8 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <Button variant="on-dark-pill" size="lg" className="h-14 px-10 text-base" asChild>
              <a href="/register">{t("ctaPrimary")}</a>
            </Button>
            <a
              href="#demo"
              className="min-h-[44px] flex items-center sh-body-md text-on-dark-mute underline underline-offset-4 hover:text-primary-foreground transition-colors"
            >
              {t("ctaSecondary")}
            </a>
          </div>
        </div>
      </div>

      {/* Gradient bridge to next section */}
      <div
        className="h-20 md:h-28 bg-gradient-to-b from-primary-deep via-primary-deep/50 to-transparent"
        aria-hidden="true"
      />

      {/* Scroll indicator */}
      <div className="hero-scroll absolute bottom-8 left-1/2 -translate-x-1/2" aria-hidden="true">
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <title>Scroll</title>
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
