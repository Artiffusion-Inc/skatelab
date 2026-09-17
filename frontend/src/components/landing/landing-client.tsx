"use client"

import Image from "next/image"
import { useRef, useState } from "react"
import { ArrowDown, ArrowUpRight, Check, Menu, X } from "lucide-react"
import FocusLock from "react-focus-lock"
import { useTranslations } from "@/i18n"
import { captureEvent } from "@/lib/posthog"

const TELEGRAM_URL = "https://t.me/SkateLabPro"
const FAQ_KEYS = [1, 2, 3, 4, 5, 6, 7] as const

function PilotLink({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    // biome-ignore lint/a11y/useValidAnchor: this is a named in-page navigation CTA
    <a
      href="#pilot"
      onClick={() => captureEvent("landing_pilot_intent", { location: "cta" })}
      className={`inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-5 py-3 sh-button-md text-primary-foreground transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.98] ${className}`}
    >
      {children}
    </a>
  )
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description?: string
}) {
  return (
    <div className="max-w-3xl">
      <p className="mb-4 sh-caption uppercase tracking-[0.14em] text-ink-mute">{eyebrow}</p>
      <h2 className="sh-display-xl text-ink">{title}</h2>
      {description && <p className="mt-5 max-w-[75ch] sh-body-lg text-ink-mute">{description}</p>}
    </div>
  )
}

type DemoTab = "video" | "data" | "coach"

function DemoSection() {
  const t = useTranslations("landing")
  const [tab, setTab] = useState<DemoTab>("video")
  const tabRefs = useRef<Record<DemoTab, HTMLButtonElement | null>>({
    video: null,
    data: null,
    coach: null,
  })
  const tabs: DemoTab[] = ["video", "data", "coach"]
  const focusTab = (nextTab: DemoTab) => {
    setTab(nextTab)
    tabRefs.current[nextTab]?.focus()
  }
  const copy = {
    video: { title: t("demoVideoTitle"), body: t("demoVideoBody") },
    data: { title: t("demoDataTitle"), body: t("demoDataBody") },
    coach: { title: t("demoCoachTitle"), body: t("demoCoachBody") },
  }[tab]

  return (
    <section
      id="demo"
      className="mx-auto max-w-6xl px-6 py-24 md:py-32"
      aria-labelledby="demo-title"
    >
      <SectionHeading
        eyebrow={t("demoEyebrow")}
        title={t("demoTitle")}
        description={t("demoDescription")}
      />
      <div className="mt-12 grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-stretch">
        <div className="relative min-h-[340px] overflow-hidden rounded-lg border border-hairline bg-ink">
          <Image
            src="/images/moodboard/visual-video.webp"
            alt=""
            fill
            sizes="(max-width: 1024px) 100vw, 60vw"
            className="object-cover opacity-45"
          />
          <div className="absolute inset-0 bg-gradient-to-tr from-ink via-ink/45 to-transparent" />
          <div className="relative flex min-h-[340px] flex-col justify-between p-6 md:p-8">
            <div className="flex items-start justify-between gap-4">
              <span className="sh-badge-opaque rounded-md px-3 py-2 text-on-dark-mute">
                {t("demoIllustration")}
              </span>
              <span className="sh-micro rounded-md bg-ink/70 px-3 py-2 text-on-dark-mute">
                {t("demoIllustrationNote")}
              </span>
            </div>
            <div className="max-w-md">
              <p className="sh-caption text-on-dark-mute">{t("demoStatus")}</p>
              <div className="mt-4 h-px w-full bg-on-dark-mute/40" aria-hidden="true" />
              <p className="mt-4 sh-body-md text-on-dark-mute">{copy.body}</p>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-hairline bg-background p-5 md:p-7">
          <div
            className="flex flex-wrap gap-2 border-b border-hairline pb-4"
            role="tablist"
            aria-label={t("demoEyebrow")}
          >
            {tabs.map(item => {
              const labels = {
                video: t("demoTabVideo"),
                data: t("demoTabData"),
                coach: t("demoTabCoach"),
              }
              return (
                <button
                  key={item}
                  type="button"
                  ref={element => {
                    tabRefs.current[item] = element
                  }}
                  id={`demo-tab-${item}`}
                  role="tab"
                  aria-selected={tab === item}
                  aria-controls="demo-panel"
                  tabIndex={tab === item ? 0 : -1}
                  onClick={() => {
                    setTab(item)
                    captureEvent("landing_demo_open", { tab: item })
                  }}
                  onKeyDown={event => {
                    const currentIndex = tabs.indexOf(item)
                    const nextIndex =
                      event.key === "ArrowRight"
                        ? (currentIndex + 1) % tabs.length
                        : event.key === "ArrowLeft"
                          ? (currentIndex - 1 + tabs.length) % tabs.length
                          : event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? tabs.length - 1
                              : -1
                    if (nextIndex >= 0) {
                      event.preventDefault()
                      focusTab(tabs[nextIndex])
                      captureEvent("landing_demo_open", { tab: tabs[nextIndex] })
                    }
                  }}
                  className={`min-h-11 rounded-md px-4 py-2 sh-button-cap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${tab === item ? "bg-primary text-primary-foreground" : "bg-canvas-soft text-ink-mute hover:text-ink"}`}
                >
                  {labels[item]}
                </button>
              )
            })}
          </div>
          <div id="demo-panel" className="py-8" role="tabpanel" aria-labelledby={`demo-tab-${tab}`}>
            <p className="sh-micro uppercase tracking-[0.12em] text-ink-mute">
              {tab === "video" ? "01" : tab === "data" ? "02" : "03"}
            </p>
            <h3 className="mt-3 sh-display-md text-ink">{copy.title}</h3>
            <p className="mt-4 max-w-[75ch] sh-body-md text-ink-mute">{copy.body}</p>
            <div className="mt-8 rounded-md border border-dashed border-hairline-dark bg-canvas-soft p-4">
              <p className="sh-caption text-ink-mute">{t("demoIllustrationNote")}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function SystemSection() {
  const t = useTranslations("landing")
  const steps = [
    { title: t("step1Title"), body: t("step1Body"), status: t("step1Status"), number: "01" },
    { title: t("step2Title"), body: t("step2Body"), status: t("step2Status"), number: "02" },
    { title: t("step3Title"), body: t("step3Body"), status: t("step3Status"), number: "03" },
  ]
  const parts = [
    { title: t("partsSensors"), body: t("partsSensorsBody") },
    { title: t("partsCapture"), body: t("partsCaptureBody") },
    { title: t("partsReview"), body: t("partsReviewBody") },
  ]

  return (
    <section
      id="how-it-works"
      className="border-t border-hairline bg-background"
      aria-labelledby="system-title"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 md:py-32">
        <SectionHeading
          eyebrow={t("systemEyebrow")}
          title={t("systemTitle")}
          description={t("systemDescription")}
        />
        <ol className="mt-14 grid gap-4 lg:grid-cols-3">
          {steps.map(step => (
            <li key={step.number} className="border-t-2 border-primary pt-5">
              <span className="sh-micro text-primary-deep">{step.number}</span>
              <h3 className="mt-8 sh-display-md text-ink">{step.title}</h3>
              <p className="mt-4 sh-body-md text-ink-mute">{step.body}</p>
              <p className="mt-8 inline-flex rounded-md bg-canvas-soft px-3 py-2 sh-micro text-ink-mute">
                {step.status}
              </p>
            </li>
          ))}
        </ol>
        <div className="mt-20 border-t border-hairline pt-8">
          <h3 className="sh-heading-lg text-ink">{t("systemPartsTitle")}</h3>
          <div className="mt-7 grid gap-8 md:grid-cols-3">
            {parts.map(part => (
              <div key={part.title}>
                <h4 className="sh-body-strong text-ink">{part.title}</h4>
                <p className="mt-2 sh-body-md text-ink-mute">{part.body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function FAQSection() {
  const t = useTranslations("landing")
  return (
    <section id="faq" className="border-t border-hairline" aria-labelledby="faq-title">
      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-24 md:py-32 lg:grid-cols-[0.8fr_1.2fr]">
        <SectionHeading eyebrow={t("faqEyebrow")} title={t("faqTitle")} />
        <div className="divide-y divide-hairline border-y border-hairline">
          {FAQ_KEYS.map(n => (
            <details key={n} className="group py-5">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-6 sh-heading-lg text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
                {t(`faqQ${n}`)}
                <span
                  className="sh-body-lg text-primary transition-transform group-open:rotate-45"
                  aria-hidden="true"
                >
                  +
                </span>
              </summary>
              <p className="max-w-[75ch] pt-3 sh-body-md text-ink-mute">{t(`faqA${n}`)}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

function Navigation() {
  const t = useTranslations("landing")
  const [open, setOpen] = useState(false)
  const links = [
    { href: "#demo", label: t("demoNav") },
    { href: "#how-it-works", label: t("howNav") },
    { href: "#pilot", label: t("pilotNav") },
  ]
  const close = () => setOpen(false)

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-hairline/80 bg-background/95 pt-[env(safe-area-inset-top)]">
      <a
        href="#main-content"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-[100] focus-visible:rounded-md focus-visible:bg-primary focus-visible:px-4 focus-visible:py-3 focus-visible:text-primary-foreground"
      >
        {t("skipToContent")}
      </a>
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <a href="#top" className="sh-heading-lg text-ink">
          SkateLab
        </a>
        <nav aria-label={t("mainNav")} className="hidden items-center gap-7 md:flex">
          {links.map(link => (
            <a
              key={link.href}
              href={link.href}
              className="min-h-11 py-3 sh-caption text-ink-mute transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <a
            href="/login"
            className="hidden min-h-11 items-center sh-caption text-ink-mute hover:text-ink md:inline-flex"
          >
            {t("signIn")}
          </a>
          <PilotLink className="hidden md:inline-flex">{t("heroCta")}</PilotLink>
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-ink focus-visible:outline-2 focus-visible:outline-ring md:hidden"
            aria-label={open ? t("menuClose") : t("menuOpen")}
            aria-expanded={open}
            onClick={() => setOpen(value => !value)}
          >
            {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>
      {open && (
        <FocusLock returnFocus>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("mobileNav")}
            className="border-t border-hairline bg-background px-6 py-5 md:hidden"
            onKeyDown={event => {
              if (event.key === "Escape") close()
            }}
          >
            <nav aria-label={t("mobileNav")} className="flex flex-col">
              {links.map(link => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={close}
                  className="min-h-11 border-b border-hairline py-3 sh-body-md text-ink"
                >
                  {link.label}
                </a>
              ))}
            </nav>
            <div className="mt-4 flex flex-col gap-2">
              <PilotLinkWithHandler className="w-full" onClick={close}>
                {t("heroCta")}
              </PilotLinkWithHandler>
              <a
                href="/login"
                onClick={close}
                className="flex min-h-11 items-center justify-center sh-body-md text-ink-mute"
              >
                {t("signIn")}
              </a>
            </div>
          </div>
        </FocusLock>
      )}
    </header>
  )
}

function PilotLinkWithHandler({
  children,
  className = "",
  onClick,
}: {
  children: React.ReactNode
  className?: string
  onClick?: () => void
}) {
  return (
    // biome-ignore lint/a11y/useValidAnchor: this is a named in-page navigation CTA
    <a
      href="#pilot"
      onClick={onClick}
      className={`inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-5 py-3 sh-button-md text-primary-foreground transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.98] ${className}`}
    >
      {children}
    </a>
  )
}

function PilotSection() {
  const t = useTranslations("landing")
  return (
    <section id="pilot" className="sh-teal-band" aria-labelledby="pilot-title">
      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-24 md:py-32 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
        <div>
          <p className="mb-4 sh-caption uppercase tracking-[0.14em] text-on-dark-mute">
            {t("pilotEyebrow")}
          </p>
          <h2 className="sh-display-lg max-w-2xl text-white" id="pilot-title">
            {t("pilotTitle")}
          </h2>
          <p className="mt-5 max-w-[65ch] sh-body-lg text-on-dark-mute">{t("pilotBody")}</p>
          <a
            href={TELEGRAM_URL}
            onClick={() =>
              captureEvent("landing_contact_click", { location: "pilot", type: "telegram" })
            }
            target="_blank"
            rel="noopener noreferrer"
            className="mt-8 inline-flex min-h-11 items-center justify-center rounded-md bg-surface-ice-soft px-5 py-3 sh-button-md text-primary-deep transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.98]"
          >
            {t("pilotCta")} <ArrowUpRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </a>
          <p className="mt-4 sh-caption text-on-dark-dim">{t("externalLink")}</p>
        </div>
        <div className="rounded-lg border border-hairline-dark bg-primary-deep/40 p-6 md:p-8">
          <p className="sh-micro uppercase tracking-[0.12em] text-on-dark-mute">
            {t("pilotChecklist")}
          </p>
          <p className="mt-8 border-t border-hairline-dark pt-5 sh-body-md text-on-dark-mute">
            {t("pilotTemplate")}
          </p>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  const t = useTranslations("landing")
  return (
    <footer className="border-t border-hairline bg-background" role="contentinfo">
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-12 md:grid-cols-[1.2fr_1fr_1fr] md:py-16">
        <div>
          <p className="sh-display-md text-ink">SkateLab</p>
          <p className="mt-2 max-w-xs sh-caption text-ink-mute">{t("footerTagline")}</p>
          <a
            href={TELEGRAM_URL}
            onClick={() =>
              captureEvent("landing_contact_click", { location: "footer", type: "telegram" })
            }
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 inline-flex min-h-11 items-center sh-button-cap text-ink underline"
          >
            Telegram <ArrowUpRight className="ml-1 h-4 w-4" aria-hidden="true" />
          </a>
        </div>
        <nav aria-label={t("footerProduct")}>
          <p className="mb-3 sh-caption text-ink-mute">{t("footerProduct")}</p>
          <div className="flex flex-col items-start">
            <a href="#demo" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerDemo")}
            </a>
            <a
              href="#how-it-works"
              className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink"
            >
              {t("footerHow")}
            </a>
            <a href="#pilot" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerPilot")}
            </a>
            <a href="/login" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerLogin")}
            </a>
          </div>
        </nav>
        <nav aria-label={t("footerLegal")}>
          <p className="mb-3 sh-caption text-ink-mute">{t("footerLegal")}</p>
          <div className="flex flex-col items-start">
            <a href="/privacy" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerPrivacy")}
            </a>
            <a href="/terms" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerTerms")}
            </a>
            <a href="/offer" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerOffer")}
            </a>
            <a href="/cookies" className="min-h-11 py-3 sh-caption text-ink-mute hover:text-ink">
              {t("footerCookiePolicy")}
            </a>
          </div>
        </nav>
      </div>
      <div className="border-t border-hairline px-6 py-5">
        <p className="mx-auto max-w-6xl sh-legal text-ink-mute">{t("footerCopyright")}</p>
      </div>
    </footer>
  )
}

export function LandingClient() {
  const t = useTranslations("landing")
  return (
    <div id="top" className="landing-page overflow-x-hidden">
      <Navigation />
      <main id="main-content" tabIndex={-1}>
        <section className="relative overflow-hidden bg-primary pt-24" aria-labelledby="hero-title">
          <div className="sh-ice-backdrop absolute inset-0" aria-hidden="true" />
          <div className="relative mx-auto grid min-h-[min(760px,calc(100svh-2rem))] max-w-6xl items-center gap-12 px-6 py-16 md:grid-cols-[1fr_0.8fr] md:py-24">
            <div className="max-w-2xl">
              <p className="sh-caption uppercase tracking-[0.14em] text-primary-foreground">
                {t("eyebrow")}
              </p>
              <h1 id="hero-title" className="mt-6 sh-display-xxl max-w-[15ch] text-ink">
                {t("headline")}
              </h1>
              <p className="mt-6 max-w-[65ch] sh-body-lg text-primary-foreground">
                {t("subtitle")}
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-5">
                <PilotLink className="rounded-full bg-surface-ice-soft text-primary-deep">
                  {t("heroCta")}
                </PilotLink>
                <a
                  href="#demo"
                  className="inline-flex min-h-11 items-center sh-body-md text-primary-foreground underline decoration-primary-foreground/50 underline-offset-4 hover:decoration-primary-foreground"
                >
                  {t("heroDemo")} <ArrowDown className="ml-2 h-4 w-4" aria-hidden="true" />
                </a>
              </div>
              <p className="mt-7 inline-flex rounded-md border border-primary-foreground/30 px-3 py-2 sh-micro text-primary-foreground">
                {t("stage")}
              </p>
            </div>
            <div className="relative min-h-[360px] overflow-hidden rounded-lg border border-primary-foreground/30 bg-ink/10 md:min-h-[500px]">
              <Image
                src="/images/moodboard/hero-desktop.webp"
                alt={t("heroAlt")}
                fill
                priority
                sizes="(max-width: 768px) 100vw, 40vw"
                className="object-cover"
              />
              <div className="absolute inset-x-4 bottom-4 rounded-md border border-on-dark-mute/40 bg-ink/75 p-4">
                <p className="sh-caption text-on-dark-mute">{t("stage")}</p>
              </div>
            </div>
          </div>
        </section>
        <DemoSection />
        <SystemSection />
        <section className="border-t border-hairline" aria-labelledby="coach-title">
          <div className="mx-auto max-w-6xl px-6 py-24 md:py-32">
            <SectionHeading
              eyebrow={t("coachEyebrow")}
              title={t("coachTitle")}
              description={t("coachDescription")}
            />
            <div className="mt-12 grid gap-6 md:grid-cols-2">
              {[
                { title: t("coachScenarioTitle"), body: t("coachScenarioBody") },
                { title: t("schoolScenarioTitle"), body: t("schoolScenarioBody") },
              ].map(scenario => (
                <article key={scenario.title} className="border-l-2 border-primary pl-6 md:pl-8">
                  <h3 className="sh-display-md text-ink">{scenario.title}</h3>
                  <p className="mt-4 max-w-[65ch] sh-body-md text-ink-mute">{scenario.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section
          className="border-t border-hairline bg-canvas-soft"
          aria-labelledby="readiness-title"
        >
          <div className="mx-auto max-w-6xl px-6 py-24 md:py-32">
            <SectionHeading
              eyebrow={t("readinessEyebrow")}
              title={t("readinessTitle")}
              description={t("readinessDescription")}
            />
            <div className="mt-12 divide-y divide-hairline border-y border-hairline">
              {[
                { label: t("readyLabel"), body: t("readyBody"), icon: Check },
                { label: t("pilotLabel"), body: t("pilotReadinessBody"), icon: ArrowUpRight },
                { label: t("plannedLabel"), body: t("plannedBody"), icon: ArrowUpRight },
              ].map(item => {
                const Icon = item.icon
                return (
                  <div
                    key={item.label}
                    className="grid gap-3 py-6 md:grid-cols-[0.35fr_1fr] md:gap-10"
                  >
                    <div className="flex items-center gap-3 sh-body-strong text-ink">
                      <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                      {item.label}
                    </div>
                    <p className="sh-body-md text-ink-mute">{item.body}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
        <FAQSection />
        <PilotSection />
      </main>
      <Footer />
      <aside
        className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-background/95 p-3 md:hidden"
        aria-label={t("mobileCta")}
      >
        <PilotLink className="w-full">{t("mobileCta")}</PilotLink>
      </aside>
    </div>
  )
}
