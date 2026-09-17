"use client"

import Image from "next/image"
import { useState } from "react"
import { ArrowDownRight, ArrowUpRight, Menu, Plus, X } from "lucide-react"
import FocusLock from "react-focus-lock"
import { useTranslations } from "@/i18n"
import { useConsent } from "@/components/consent-provider"
import { captureEvent } from "@/lib/posthog"

const STORY_KEYS = ["capture", "sense", "review"] as const

type StoryKey = (typeof STORY_KEYS)[number]

function PilotLink({
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
      className={`landing-button landing-button-signal ${className}`}
    >
      {children}
      <ArrowUpRight aria-hidden="true" className="h-4 w-4" />
    </a>
  )
}

function Navigation() {
  const t = useTranslations("landing")
  const [open, setOpen] = useState(false)
  const links = [
    { href: "#story", label: t("navStory") },
    { href: "#review", label: t("navReview") },
    { href: "#pilot", label: t("navPilot") },
  ]
  const close = () => setOpen(false)

  return (
    <header className="landing-nav">
      <a href="#main-content" className="landing-skip-link">
        {t("skipToContent")}
      </a>
      <div className="landing-nav-inner">
        <a href="#top" className="landing-wordmark" aria-label="SkateLab">
          Skate<span>Lab</span>
        </a>
        <nav className="landing-desktop-nav" aria-label={t("mainNav")}>
          {links.map(link => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        <div className="landing-nav-actions">
          <PilotLink className="landing-nav-cta">{t("navCta")}</PilotLink>
          <button
            type="button"
            className="landing-menu-button"
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
            className="landing-mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label={t("mobileNav")}
            onKeyDown={event => {
              if (event.key === "Escape") close()
            }}
          >
            <nav aria-label={t("mobileNav")}>
              {links.map(link => (
                <a key={link.href} href={link.href} onClick={close}>
                  {link.label}
                </a>
              ))}
            </nav>
            <PilotLink className="landing-mobile-cta" onClick={close}>
              {t("navCta")}
            </PilotLink>
          </div>
        </FocusLock>
      )}
    </header>
  )
}

function StorySection() {
  const t = useTranslations("landing")
  const [active, setActive] = useState<StoryKey>("capture")
  const details = {
    capture: { title: t("storyCaptureTitle"), body: t("storyCaptureBody") },
    sense: { title: t("storySenseTitle"), body: t("storySenseBody") },
    review: { title: t("storyReviewTitle"), body: t("storyReviewBody") },
  }[active]

  return (
    <section id="story" className="landing-story" aria-labelledby="story-title">
      <div className="landing-section-head">
        <h2 id="story-title">{t("storyTitle")}</h2>
        <p>{t("storyIntro")}</p>
      </div>
      <div className="landing-story-grid">
        <div className="landing-story-media">
          <Image
            src="/images/landing/blade-macro.webp"
            alt={t("bladeAlt")}
            fill
            sizes="(max-width: 800px) 100vw, 48vw"
            className="landing-cover"
          />
        </div>
        <div className="landing-story-copy">
          <p className="landing-story-index" aria-hidden="true">
            0{STORY_KEYS.indexOf(active) + 1} / 03
          </p>
          <h3>{details.title}</h3>
          <p>{details.body}</p>
          <div className="landing-story-tabs" role="tablist" aria-label={t("storyTabsLabel")}>
            {STORY_KEYS.map((key, index) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active === key}
                aria-controls="story-panel"
                id={`story-tab-${key}`}
                tabIndex={active === key ? 0 : -1}
                onClick={() => {
                  setActive(key)
                  captureEvent("landing_story_open", { step: key })
                }}
                onKeyDown={event => {
                  const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0
                  const nextIndex =
                    event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? STORY_KEYS.length - 1
                        : offset
                          ? (index + offset + STORY_KEYS.length) % STORY_KEYS.length
                          : -1
                  if (nextIndex < 0) return
                  event.preventDefault()
                  const next = STORY_KEYS[nextIndex]
                  setActive(next)
                  document.getElementById(`story-tab-${next}`)?.focus()
                }}
              >
                <span>0{index + 1}</span>
                {t(
                  `storyTab${key[0].toUpperCase()}${key.slice(1)}` as
                    | "storyTabCapture"
                    | "storyTabSense"
                    | "storyTabReview",
                )}
              </button>
            ))}
          </div>
          <div
            id="story-panel"
            role="tabpanel"
            aria-labelledby={`story-tab-${active}`}
            className="landing-story-status"
          >
            <span className="landing-status-dot" aria-hidden="true" />
            {t("storyStatus")}
          </div>
        </div>
      </div>
    </section>
  )
}

function ReviewSection() {
  const t = useTranslations("landing")
  return (
    <section id="review" className="landing-review" aria-labelledby="review-title">
      <div className="landing-review-image">
        <Image
          src="/images/landing/coach-review.webp"
          alt={t("coachImageAlt")}
          fill
          sizes="(max-width: 800px) 100vw, 58vw"
          className="landing-cover"
        />
      </div>
      <div className="landing-review-copy">
        <h2 id="review-title">{t("reviewTitle")}</h2>
        <p className="landing-review-lead">{t("reviewLead")}</p>
        <ol className="landing-review-list">
          <li>
            <span>01</span>
            <p>
              <strong>{t("reviewOneTitle")}</strong>
              {t("reviewOneBody")}
            </p>
          </li>
          <li>
            <span>02</span>
            <p>
              <strong>{t("reviewTwoTitle")}</strong>
              {t("reviewTwoBody")}
            </p>
          </li>
          <li>
            <span>03</span>
            <p>
              <strong>{t("reviewThreeTitle")}</strong>
              {t("reviewThreeBody")}
            </p>
          </li>
        </ol>
      </div>
    </section>
  )
}

function PilotSection() {
  const t = useTranslations("landing")
  return (
    <section id="pilot" className="landing-pilot" aria-labelledby="pilot-title">
      <div className="landing-pilot-content">
        <h2 id="pilot-title">{t("pilotTitle")}</h2>
        <p>{t("pilotBody")}</p>
        <p
          className="landing-button landing-button-paper landing-button-disabled"
          aria-disabled="true"
        >
          {t("pilotCtaPending")}
        </p>
        <p className="landing-pilot-note">{t("pilotNote")}</p>
      </div>
      <div className="landing-pilot-side">
        <p>{t("pilotChecklistTitle")}</p>
        <ul>
          <li>{t("pilotChecklistOne")}</li>
          <li>{t("pilotChecklistTwo")}</li>
          <li>{t("pilotChecklistThree")}</li>
        </ul>
      </div>
    </section>
  )
}

function QuestionsSection() {
  const t = useTranslations("landing")
  const questions = [1, 2, 3]
  return (
    <section className="landing-questions" aria-labelledby="questions-title">
      <div>
        <h2 id="questions-title">{t("questionsTitle")}</h2>
      </div>
      <div className="landing-question-list">
        {questions.map(number => (
          <details key={number}>
            <summary>
              {t(`question${number}` as "question1" | "question2" | "question3")}
              <Plus aria-hidden="true" />
            </summary>
            <p>{t(`answer${number}` as "answer1" | "answer2" | "answer3")}</p>
          </details>
        ))}
      </div>
    </section>
  )
}

function Footer() {
  const t = useTranslations("landing")
  const { openBanner } = useConsent()
  return (
    <footer className="landing-footer">
      <div className="landing-footer-top">
        <a href="#top" className="landing-wordmark">
          Skate<span>Lab</span>
        </a>
        <p>{t("footerTagline")}</p>
        <span>{t("telegramPending")}</span>
      </div>
      <div className="landing-footer-bottom">
        <span>{t("footerCopyright")}</span>
        <nav aria-label={t("footerLegal")}>
          <a href="/privacy">{t("footerPrivacy")}</a>
          <a href="/terms">{t("footerTerms")}</a>
          <a href="/offer">{t("footerOffer")}</a>
          <a href="/cookies">{t("footerCookiePolicy")}</a>
          <button type="button" onClick={openBanner} className="landing-footer-cookie-settings">
            {t("footerCookieSettings")}
          </button>
        </nav>
      </div>
    </footer>
  )
}

export function LandingClient() {
  const t = useTranslations("landing")
  return (
    <div id="top" className="landing-page">
      <Navigation />
      <main id="main-content" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="hero-title">
          <Image
            src="/images/landing/hero-rink.webp"
            alt={t("heroAlt")}
            fill
            priority
            sizes="100vw"
            className="landing-hero-image"
          />
          <div className="landing-hero-shade" aria-hidden="true" />
          <div className="landing-hero-content">
            <p className="landing-kicker">{t("heroKicker")}</p>
            <h1 id="hero-title">
              <span>{t("heroTitleLine1")}</span> <span>{t("heroTitleLine2")}</span>{" "}
              <span>{t("heroTitleLine3")}</span>
            </h1>
            <p className="landing-hero-lead">{t("heroLead")}</p>
            <div className="landing-hero-actions">
              <PilotLink onClick={() => captureEvent("landing_pilot_intent", { location: "hero" })}>
                {t("heroCta")}
              </PilotLink>
              <a href="#story" className="landing-text-link">
                {t("heroSecondary")} <ArrowDownRight aria-hidden="true" className="h-4 w-4" />
              </a>
            </div>
            <p className="landing-stage">
              <span aria-hidden="true" />
              {t("stage")}
            </p>
          </div>
        </section>
        <StorySection />
        <ReviewSection />
        <QuestionsSection />
        <PilotSection />
      </main>
      <Footer />
    </div>
  )
}
