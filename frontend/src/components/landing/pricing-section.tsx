"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"
import { Check } from "lucide-react"

export function PricingSection() {
  const t = useTranslations("landing")

  const hardware = {
    name: t("pricingHardwareName"),
    price: t("pricingHardwarePrice"),
    desc: t("pricingHardwareDesc"),
    features: t("pricingHardwareFeatures").split("|"),
    cta: t("pricingHardwareCta"),
    href: t("pricingHardwareHref"),
  }

  const saasTiers = [
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
      href: "/register",
      highlighted: true,
      badge: t("pricingProBadge"),
    },
    {
      name: t("pricingCoachName"),
      price: t("pricingCoachPrice"),
      desc: t("pricingCoachDesc"),
      features: t("pricingCoachFeatures").split("|"),
      cta: t("pricingCoachCta"),
      href: t("pricingCoachHref"),
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
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("pricingTitle")}
        </p>
        <h2 id="pricing-heading" className="sh-display-xl text-ink">
          {t("pricingHeadline")}
        </h2>
      </div>

      <div className="pricing-card relative mb-10 overflow-hidden rounded-lg border border-primary bg-canvas-soft p-8 lg:p-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="sh-display-md text-ink">{hardware.name}</h3>
              <span className="sh-badge-opaque inline-flex items-center rounded-full px-3 py-1 sh-micro text-primary-foreground">
                {hardware.price}
              </span>
            </div>
            <p className="sh-body-md text-ink-mute">{hardware.desc}</p>
            <ul className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {hardware.features.map(f => (
                <li key={f} className="flex items-center gap-2 sh-caption text-ink-mute">
                  <Check className="h-4 w-4 text-score-good shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <Button
            variant="default"
            size="lg"
            className="min-h-[44px] px-8 shrink-0"
            asChild
          >
            <a
              href={hardware.href}
              target="_blank"
              rel="noopener noreferrer"
            >
              {hardware.cta}
            </a>
          </Button>
        </div>
      </div>

      <ul className="grid gap-8 lg:grid-cols-3">
        {saasTiers.map(tier => (
          <li
            key={tier.name}
            className={`pricing-card relative rounded-lg p-8 ${
              tier.highlighted
                ? "bg-primary-foreground border-2 border-primary"
                : "border border-hairline bg-background"
            }`}
          >
            {tier.badge && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary px-3 py-1 rounded-full sh-micro text-primary-foreground tracking-wider">
                {tier.badge}
              </span>
            )}
            <h3 className="sh-heading-lg text-ink">{tier.name}</h3>
            <p className="sh-price mt-4 text-ink">
              <data value={tier.price.replace(/[^\d]/g, "")}>{tier.price}</data>
            </p>
            <p className="mt-2 sh-caption text-ink-mute">{tier.desc}</p>
            <ul className="mt-6 space-y-3">
              {tier.features.map(f => (
                <li
                  key={f}
                  className="flex items-start gap-2 sh-caption text-ink-mute"
                >
                  <Check
                    className={`h-4 w-4 mt-0.5 shrink-0 ${tier.highlighted ? "text-primary" : "text-score-good"}`}
                  />
                  {f}
                </li>
              ))}
            </ul>
            <Button
              variant={tier.highlighted ? "default" : "outline"}
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

      <p className="mt-8 text-center sh-legal text-ink-mute">
        {t("pricingHardwareNote")}
      </p>
    </section>
  )
}
