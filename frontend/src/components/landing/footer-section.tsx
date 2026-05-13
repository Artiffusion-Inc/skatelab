"use client"

import { useTranslations } from "@/i18n"

export function FooterSection() {
  const t = useTranslations("landing")

  return (
    <footer role="contentinfo" className="border-t border-hairline bg-background">
      <div className="mx-auto max-w-5xl px-6 py-12 md:py-16 lg:grid lg:grid-cols-2 lg:gap-10">
        <div className="lg:col-span-1">
          <p className="sh-display-md text-ink">SkateLab</p>
          <p className="sh-caption text-ink-mute mt-1">{t("footerTagline")}</p>
          <a
            href="https://t.me/SkateLabPro"
            target="_blank"
            rel="noopener noreferrer"
            className="sh-button-cap text-ink underline hover:text-ink-mute mt-2 inline-block min-h-[44px] leading-[44px]"
          >
            {t("ctaPrimary")} →
          </a>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-6 lg:mt-0">
          <nav aria-label={t("footerProduct")}>
            <h3 className="mb-2 sh-caption text-muted-foreground">
              {t("footerProduct")}
            </h3>
            <ul className="flex flex-col gap-1">
              <li>
                <a
                  href="#features"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerFeatures")}
                </a>
              </li>
              <li>
                <a
                  href="#how-it-works"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerHowItWorks")}
                </a>
              </li>
              <li>
                <a
                  href="#pricing"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerPricing")}
                </a>
              </li>
              <li>
                <a
                  href="#faq"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerFaq")}
                </a>
              </li>
            </ul>
          </nav>

          <nav aria-label={t("footerLegal")}>
            <h3 className="mb-2 sh-caption text-muted-foreground">
              {t("footerLegal")}
            </h3>
            <ul className="flex flex-col gap-1">
              <li>
                <a
                  href="/privacy"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerPrivacy")}
                </a>
              </li>
              <li>
                <a
                  href="/terms"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerTerms")}
                </a>
              </li>
              <li>
                <a
                  href="/offer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerOffer")}
                </a>
              </li>
              <li>
                <a
                  href="/cookies"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  {t("footerCookiePolicy")}
                </a>
              </li>
            </ul>
          </nav>

          <section aria-label={t("footerContact")}>
            <h3 className="mb-2 sh-caption text-muted-foreground">
              {t("footerContact")}
            </h3>
            <ul className="flex flex-col gap-1">
              <li>
                <a
                  href="https://t.me/SkateLabPro"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  Telegram
                </a>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6 border-t border-hairline pt-5 pb-8 flex justify-between items-center">
        <p className="sh-caption text-ink-mute">{t("footerCopyright")}</p>
      </div>
    </footer>
  )
}
