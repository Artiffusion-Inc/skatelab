"use client"

import Image from "next/image"
import { ArrowDownRight, Plus } from "lucide-react"
import { useTranslations } from "@/i18n"
import { PublicShell, ContactLink, ContactClose } from "./public-shell"
import { HomeJourney, HomeEditorial, HomeEquipment } from "./public-pages"

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

export function LandingClient() {
  const t = useTranslations("landing")
  return (
    <PublicShell home>
      <main id="main-content" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="hero-title">
          <Image
            src="/images/landing/hero-rink.webp"
            alt={t("heroAlt")}
            fill
            priority
            fetchPriority="high"
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
              <ContactLink>{t("heroCta")}</ContactLink>
              <a href="/how-it-works" className="landing-text-link">
                {t("heroSecondary")} <ArrowDownRight aria-hidden="true" className="h-4 w-4" />
              </a>
            </div>
            <p className="landing-stage">
              <span aria-hidden="true" />
              {t("stage")}
            </p>
          </div>
        </section>
        <HomeJourney />
        <ReviewSection />
        <HomeEquipment />
        <HomeEditorial />
        <QuestionsSection />
        <ContactClose />
      </main>
    </PublicShell>
  )
}
