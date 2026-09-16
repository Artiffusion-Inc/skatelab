import type { Metadata } from "next"
import { getTranslations } from "next-intl/server"
import { LandingClient } from "@/components/landing/landing-client"

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "SkateLab для школ фигурного катания",
    description:
      "Система датчиков и видеоанализа для разбора техники фигуристов. Обсудите с SkateLab пилот для вашей школы.",
    alternates: { canonical: "https://skatelab.ru" },
    openGraph: {
      title: "SkateLab для школ фигурного катания",
      description:
        "Система датчиков и видеоанализа для разбора техники фигуристов. Обсудите пилот для вашей школы.",
      url: "https://skatelab.ru",
      siteName: "SkateLab",
      locale: "ru_RU",
      type: "website",
      images: [
        {
          url: "https://skatelab.ru/images/moodboard/hero-desktop.webp",
          width: 1200,
          height: 630,
          alt: "Фигурист на тренировке",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "SkateLab для школ фигурного катания",
      description:
        "Система датчиков и видеоанализа для разбора техники фигуристов. Обсудите пилот для вашей школы.",
      images: ["https://skatelab.ru/images/moodboard/hero-desktop.webp"],
    },
  }
}

export default async function LandingPage() {
  const t = await getTranslations("landing")
  const faqItems = [1, 2, 3, 4, 5, 6, 7].map(n => ({
    q: t(`faqQ${n}`),
    a: t(`faqA${n}`),
  }))
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: faqItems.map(item => ({
        "@type": "Question",
        name: item.q,
        acceptedAnswer: { "@type": "Answer", text: item.a },
      })),
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "SkateLab",
      url: "https://skatelab.ru",
    },
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "SkateLab",
      url: "https://skatelab.ru",
    },
  ]

  return (
    <>
      {jsonLd.map(schema => (
        <script
          key={schema["@type"]}
          type="application/ld+json"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: JSON-LD structured data for SEO
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
      <div id="landing-nojs-fallback">
        <main className="mx-auto max-w-3xl px-6 py-16" aria-labelledby="noscript-title">
          <p className="sh-caption text-ink-mute">{t("stage")}</p>
          <h1 id="noscript-title" className="mt-4 sh-display-xl text-ink">
            {t("headline")}
          </h1>
          <p className="mt-5 sh-body-lg text-ink-mute">{t("subtitle")}</p>
          <section
            className="mt-16 border-t border-hairline pt-8"
            aria-labelledby="noscript-demo-title"
          >
            <h2 id="noscript-demo-title" className="sh-heading-lg text-ink">
              {t("demoTitle")}
            </h2>
            <p className="mt-3 sh-body-md text-ink-mute">{t("demoDescription")}</p>
          </section>
          <a
            href="https://t.me/SkateLabPro"
            className="mt-7 inline-flex min-h-11 items-center rounded-md bg-primary px-5 py-3 sh-button-md text-primary-foreground"
          >
            {t("pilotCta")}
          </a>
        </main>
      </div>
      <LandingClient />
    </>
  )
}
