"use client"

import Image from "next/image"
import { ArrowUpRight, Plus } from "lucide-react"
import { useLocale, useTranslations } from "@/i18n"
import { blogUrl } from "@/lib/public-site"
import { resolveLocale } from "@/lib/docs-i18n"
import { ContactClose, ContactLink, PublicShell } from "./public-shell"
import { EquipmentDiagram, PhaseExplorer, ReviewWorkspace, SkaterTrace } from "./movement-scenes"

function ArticleLink({ slug, children }: { slug: string; children: React.ReactNode }) {
  const locale = resolveLocale(useLocale())
  return (
    <a href={blogUrl(locale, [slug])} className="public-text-link">
      {children}
      <ArrowUpRight size={18} aria-hidden="true" />
    </a>
  )
}

function EditorialImage({
  image,
  alt,
  className = "",
}: {
  image: string
  alt: string
  className?: string
}) {
  return (
    <div className={`public-editorial-image ${className}`}>
      <Image
        src={`/images/landing/${image}.webp`}
        alt={alt}
        fill
        sizes="(max-width: 800px) 100vw, 55vw"
        className="landing-cover"
      />
    </div>
  )
}

export function PublicFAQ({ kind }: { kind: "equipment" | "contact" | "process" }) {
  const t = useTranslations("publicSite")
  const l = useTranslations("landing")
  return (
    <section id="faq" className="landing-questions public-section" aria-labelledby="faq-title">
      <h2 id="faq-title">{t("faqTitle")}</h2>
      <div className="landing-question-list">
        {[0, 1, 2].map(index => (
          <details key={index}>
            <summary>
              {kind === "process" ? l(`question${index + 1}`) : t(`${kind}Question${index}`)}
              <Plus aria-hidden="true" />
            </summary>
            <p>{kind === "process" ? l(`answer${index + 1}`) : t(`${kind}Answer${index}`)}</p>
          </details>
        ))}
      </div>
    </section>
  )
}

export function HomeJourney() {
  const t = useTranslations("publicSite")
  return (
    <section id="story" className="public-section home-journey">
      <div className="public-section-heading">
        <h2>{t("homeTrackTitle")}</h2>
        <p>{t("homeTrackIntro")}</p>
      </div>
      <ol className="public-journey-stops">
        {[0, 1, 2].map(index => (
          <li key={index}>
            <span>0{index + 1}</span>
            <h3>{t(`homeStep${index}`)}</h3>
            <p>{t(`homeStepBody${index}`)}</p>
          </li>
        ))}
      </ol>
      <a href="/how-it-works" className="home-trace-link">
        <SkaterTrace active={2} />
        <span className="public-text-link">
          {t("homeProcessLink")}
          <ArrowUpRight size={20} aria-hidden="true" />
        </span>
      </a>
    </section>
  )
}

export function HomeEquipment() {
  const t = useTranslations("publicSite")
  const l = useTranslations("landing")
  return (
    <section className="public-equipment-teaser">
      <EditorialImage image="blade-macro" alt={l("bladeAlt")} />
      <div>
        <p className="public-eyebrow">{t("equipmentKicker")}</p>
        <h2>{t("equipmentTitle")}</h2>
        <p>{t("equipmentIntro")}</p>
        <a href="/equipment" className="public-text-link">
          {t("homeEquipmentLink")}
          <ArrowUpRight size={18} aria-hidden="true" />
        </a>
      </div>
    </section>
  )
}

export function HomeEditorial() {
  const t = useTranslations("publicSite")
  return (
    <section className="public-section home-editorial">
      <div>
        <p className="public-eyebrow">{t("blogKicker")}</p>
        <h2>{t("homeJournalTitle")}</h2>
        <p>{t("homeJournalBody")}</p>
        <ArticleLink slug="recording-guide">{t("readMore")}</ArticleLink>
      </div>
      <EditorialImage image="recording-guide" alt={t("recordingAlt")} />
    </section>
  )
}

export function ProcessPage() {
  const t = useTranslations("publicSite")
  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1}>
        <section className="public-page-intro">
          <p className="public-eyebrow">{t("processKicker")}</p>
          <h1>{t("processTitle")}</h1>
          <p>{t("processIntro")}</p>
          <nav className="public-chapters" aria-label={t("navProcess")}>
            {["Capture", "Phases", "Review", "Task"].map((key, index) => (
              <a key={key} href={`#${key.toLowerCase()}`}>
                <span>0{index + 1}</span>
                {t(`chapter${key}`)}
              </a>
            ))}
          </nav>
        </section>
        <section id="capture" className="public-capture public-section">
          <EditorialImage image="recording-guide" alt={t("recordingAlt")} />
          <div>
            <p className="public-eyebrow">01 / {t("chapterCapture")}</p>
            <h2>{t("captureTitle")}</h2>
            <p>{t("captureBody")}</p>
            <ArticleLink slug="recording-guide">{t("captureLink")}</ArticleLink>
          </div>
        </section>
        <section id="phases" className="public-section public-phase-section">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">02 / {t("chapterPhases")}</p>
              <h2>{t("phaseTitle")}</h2>
            </div>
            <p>{t("phaseIntro")}</p>
          </div>
          <PhaseExplorer />
        </section>
        <section id="review" className="public-section public-review-section">
          <div className="public-section-heading">
            <div>
              <p className="public-eyebrow">03 / {t("chapterReview")}</p>
              <h2>{t("reviewTitle")}</h2>
            </div>
            <p>{t("reviewIntro")}</p>
          </div>
          <ReviewWorkspace />
        </section>
        <section id="task" className="public-section public-task">
          <div>
            <p className="public-eyebrow">04 / {t("chapterTask")}</p>
            <h2>{t("taskTitle")}</h2>
            <p>{t("taskBody")}</p>
            <ArticleLink slug="coach-feedback">{t("taskLink")}</ArticleLink>
          </div>
          <EditorialImage image="training-notes" alt={t("notesAlt")} />
        </section>
        <aside className="public-limits">
          <h2>{t("limitsTitle")}</h2>
          <p>{t("limitsBody")}</p>
          <ArticleLink slug="video-and-sensors">{t("readMore")}</ArticleLink>
        </aside>
        <PublicFAQ kind="process" />
        <ContactClose />
      </main>
    </PublicShell>
  )
}

export function EquipmentPage() {
  const t = useTranslations("publicSite")
  const l = useTranslations("landing")
  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1}>
        <section className="public-page-intro">
          <p className="public-eyebrow">{t("equipmentKicker")}</p>
          <h1>{t("equipmentTitle")}</h1>
          <p>{t("equipmentIntro")}</p>
        </section>
        <section className="public-section equipment-sources">
          <div className="public-section-heading">
            <h2>{t("equipmentSceneTitle")}</h2>
            <p>{t("equipmentSceneIntro")}</p>
          </div>
          <div className="equipment-source-grid">
            <EditorialImage image="blade-macro" alt={l("bladeAlt")} />
            <EquipmentDiagram />
          </div>
        </section>
        <section className="public-section public-comparison">
          <h2>{t("compareTitle")}</h2>
          <div className="public-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("compareAspect")}</th>
                  <th scope="col">{t("compareVideo")}</th>
                  <th scope="col">{t("compareSensor")}</th>
                </tr>
              </thead>
              <tbody>
                {[0, 1, 2].map(index => (
                  <tr key={index}>
                    <th scope="row">{t(`compareRow${index}`)}</th>
                    <td>{t(`compareV${index}`)}</td>
                    <td>{t(`compareS${index}`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ArticleLink slug="video-and-sensors">{t("readMore")}</ArticleLink>
        </section>
        <section className="public-section public-setup">
          <div>
            <h2>{t("setupTitle")}</h2>
            <ol>
              {[0, 1, 2, 3].map(index => (
                <li key={index}>
                  <span>0{index + 1}</span>
                  <p>{t(`setup${index}`)}</p>
                </li>
              ))}
            </ol>
            <ArticleLink slug="recording-guide">{t("captureLink")}</ArticleLink>
          </div>
          <EditorialImage image="recording-guide" alt={t("recordingAlt")} />
        </section>
        <aside className="public-limits">
          <h2>{t("hardwareTitle")}</h2>
          <p>{t("hardwareBody")}</p>
        </aside>
        <PublicFAQ kind="equipment" />
        <ContactClose />
      </main>
    </PublicShell>
  )
}

export function ContactPage() {
  const t = useTranslations("publicSite")
  return (
    <PublicShell>
      <main id="main-content" tabIndex={-1}>
        <section className="public-page-intro public-contact-intro">
          <p className="public-eyebrow">{t("contactKicker")}</p>
          <h1>{t("contactTitle")}</h1>
          <p>{t("contactIntro")}</p>
        </section>
        <section className="public-contact-panel">
          <div>
            <span className="public-contact-arrow" aria-hidden="true">
              ↗
            </span>
            <h2>{t("contactDirect")}</h2>
            <ContactLink className="landing-button-paper" />
          </div>
          <div>
            <p>{t("contactBody")}</p>
            <p className="public-contact-privacy">{t("contactPrivacy")}</p>
          </div>
        </section>
        <section className="public-section public-audiences">
          {[0, 1, 2].map(index => (
            <div key={index}>
              <span className="public-eyebrow">0{index + 1}</span>
              <h2>{t(`audience${index}`)}</h2>
              <p>{t(`audienceBody${index}`)}</p>
            </div>
          ))}
        </section>
        <PublicFAQ kind="contact" />
      </main>
    </PublicShell>
  )
}
