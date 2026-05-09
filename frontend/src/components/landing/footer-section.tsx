"use client"

import { useTranslations } from "@/i18n"

export function FooterSection() {
  const t = useTranslations("landing")

  return (
    <footer role="contentinfo" className="border-t border-hairline bg-background">
      <div className="mx-auto max-w-5xl px-6 py-12 md:py-16">
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="sh-display-md text-ink">SkateLab</p>
            <p className="sh-caption text-ink-mute mt-1">{t("footerTagline")}</p>
            <a
              href="/register"
              className="sh-button-cap text-link hover:underline mt-2 inline-block min-h-[44px] flex items-center"
            >
              {t("ctaPrimary")} →
            </a>
          </div>

          <nav aria-label={t("footerProduct")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerProduct")}</p>
            <ul className="space-y-2">
              <li>
                <a href="#how-it-works" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerHowItWorks")}
                </a>
              </li>
              <li>
                <a href="#pricing" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerPricing")}
                </a>
              </li>
              <li>
                <a href="#faq" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerFaq")}
                </a>
              </li>
            </ul>
          </nav>

          <nav aria-label={t("footerLegal")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerLegal")}</p>
            <ul className="space-y-2">
              <li>
                <a href="/privacy" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerPrivacy")}
                </a>
              </li>
              <li>
                <a href="/terms" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerTerms")}
                </a>
              </li>
              <li>
                <a href="/offer" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerOffer")}
                </a>
              </li>
              <li>
                <a href="/cookies" className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center">
                  {t("footerCookiePolicy")}
                </a>
              </li>
            </ul>
          </nav>

          <div aria-label={t("footerContact")}>
            <p className="sh-button-cap text-ink-mute mb-3">{t("footerContact")}</p>
            <ul className="space-y-2">
              <li>
                <a
                  href="https://t.me/SkateLabBot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  Telegram
                </a>
              </li>
              <li>
                <a
                  href="https://vk.com/skatelab"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sh-caption text-ink-mute hover:text-ink min-h-[44px] flex items-center"
                >
                  VK
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 border-t border-hairline pt-6">
          <p className="sh-legal text-ink-mute">{t("footerCopyright")}</p>
        </div>
      </div>
    </footer>
  )
}
