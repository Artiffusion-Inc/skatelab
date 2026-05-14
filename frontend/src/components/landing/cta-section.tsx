"use client"

import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

export function CTASection() {
  const t = useTranslations("landing")

  return (
    <section className="cta-section sh-teal-band" aria-labelledby="cta-heading">
      <div className="relative mx-auto max-w-5xl px-6 py-24 md:py-32">
        <div className="max-w-lg">
          <p className="mb-4 sh-caption text-primary-foreground/70">{t("ctaEyebrow")}</p>
          <h2 id="cta-heading" className="sh-display-lg text-primary-foreground max-w-[65ch]">
            {t("ctaHeadlineNew")}
          </h2>
          <p className="mt-4 sh-body-lg text-primary-foreground/70 max-w-[65ch]">
            {t("ctaSubtitleNew")}
          </p>
          <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row">
            <Button
              variant="on-dark-pill"
              size="lg"
              className="min-h-[44px] px-10 text-base"
              asChild
            >
              <a href="https://t.me/SkateLabPro" target="_blank" rel="noopener noreferrer">
                {t("ctaPrimary")}
              </a>
            </Button>
            <a
              href="/register"
              className="min-h-[44px] py-2.5 flex items-center sh-body-md text-primary-foreground/70 underline hover:text-primary-foreground"
            >
              {t("ctaSecondary")}
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
