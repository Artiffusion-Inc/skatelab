"use client"

import Image from "next/image"
import Link from "next/link"
import { ArrowDownRight, Plus } from "lucide-react"
import { useTranslations } from "@/i18n"
import { PublicShell, ContactLink, ContactClose } from "./public-shell"
import { HomeJourney, HomeEditorial, HomeEquipment } from "./public-pages"

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
            <h1 id="hero-title">
              <span>{t("heroTitleLine1")}</span> <span>{t("heroTitleLine2")}</span>{" "}
              <span>{t("heroTitleLine3")}</span>
            </h1>
            <p className="landing-hero-lead">{t("heroLead")}</p>
            <div className="landing-hero-actions">
              <ContactLink>{t("heroCta")}</ContactLink>
              <Link href="#story" className="landing-text-link">
                {t("heroSecondary")} <ArrowDownRight aria-hidden="true" className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>
        <HomeJourney />
        <HomeEquipment />
        <HomeEditorial />
        <QuestionsSection />
        <ContactClose />
      </main>
    </PublicShell>
  )
}
