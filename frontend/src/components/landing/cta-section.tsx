"use client"

import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

export function CTASection() {
  const t = useTranslations("landing")

  return (
    <section className="cta-section sh-teal-band" aria-labelledby="cta-heading">
      <div className="relative mx-auto max-w-5xl px-6 py-24 md:py-32">
        <div className="max-w-lg">
          <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-on-dark-mute">
            {t("ctaEyebrow")}
          </p>
          <h2 id="cta-heading" className="sh-display-lg text-primary-foreground">
            {t("ctaHeadlineNew")}
          </h2>
          <p className="mt-4 sh-body-lg text-on-dark-mute">
            {t("ctaSubtitleNew")}
          </p>
          <div className="mt-10 flex flex-col items-start gap-4 sm:flex-row">
            <Button
              variant="on-dark-pill"
              size="lg"
              className="min-h-[44px] px-10 text-base"
              asChild
            >
              <a href="/register">
                {t("ctaPrimary")}
              </a>
            </Button>
            <a
              href="/login"
              className="min-h-[44px] flex items-center sh-body-md text-on-dark-mute underline hover:text-primary-foreground"
            >
              {t("ctaHasAccount")}
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
