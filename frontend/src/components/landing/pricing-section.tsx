"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"
import { Check } from "lucide-react"

export function PricingSection() {
  const t = useTranslations("landing")

  const tiers = [
    {
      name: t("pricingFreeName"),
      price: t("pricingFreePrice"),
      desc: t("pricingFreeDesc"),
      features: t("pricingFreeFeatures").split("|"),
      cta: t("pricingFreeCta"),
      href: "/register",
      highlighted: false,
    },
    {
      name: t("pricingProName"),
      price: t("pricingProPrice"),
      desc: t("pricingProDesc"),
      features: t("pricingProFeatures").split("|"),
      cta: t("pricingProCta"),
      href: "https://t.me/SkateLabPro",
      highlighted: true,
      badge: t("pricingProBadge"),
    },
    {
      name: t("pricingCoachName"),
      price: t("pricingCoachPrice"),
      desc: t("pricingCoachDesc"),
      features: t("pricingCoachFeatures").split("|"),
      cta: t("pricingCoachCta"),
      href: "https://t.me/SkateLabBot",
      highlighted: false,
    },
  ]

  return (
    <section
      id="pricing"
      tabIndex={-1}
      className="border-t border-hairline mx-auto max-w-5xl px-6 py-16 md:py-24"
      aria-labelledby="pricing-heading"
    >
      <div className="mb-14 md:mb-20 text-center">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("pricingTitle")}
        </p>
        <h2 id="pricing-heading" className="sh-display-xl text-ink">
          {t("pricingTitle")}
        </h2>
      </div>

      <ul className="grid gap-8 lg:grid-cols-3">
        {tiers.map(tier => (
          <li
            key={tier.name}
            className={`pricing-card relative rounded-lg p-8 ${
              tier.highlighted
                ? "bg-primary text-primary-foreground border border-primary"
                : "border border-hairline bg-background text-ink"
            }`}
          >
            {tier.badge && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-surface-violet-soft px-3 py-1 rounded-full sh-micro text-primary-deep tracking-wider">
                {tier.badge}
              </span>
            )}
            <h3 className="sh-heading-lg">{tier.name}</h3>
            <p className="sh-price mt-4">
              <data value={tier.price.replace(/[^\d]/g, "")}>{tier.price}</data>
            </p>
            <p
              className={`mt-2 sh-caption ${tier.highlighted ? "text-on-dark-mute" : "text-ink-mute"}`}
            >
              {tier.desc}
            </p>
            <ul className="mt-6 space-y-3">
              {tier.features.map(f => (
                <li
                  key={f}
                  className={`flex items-start gap-2 sh-caption ${tier.highlighted ? "text-on-dark-mute" : "text-ink-mute"}`}
                >
                  <Check
                    className={`h-4 w-4 mt-0.5 shrink-0 ${tier.highlighted ? "text-surface-violet-soft" : "text-score-good"}`}
                  />
                  {f}
                </li>
              ))}
            </ul>
            <Button
              variant={tier.highlighted ? "on-teal" : "outline"}
              className="mt-6 min-h-[44px] w-full"
              asChild
            >
              <a
                href={tier.href}
                {...(tier.href.startsWith("http")
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
              >
                {tier.cta}
              </a>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}
