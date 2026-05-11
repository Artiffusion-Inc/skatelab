import type { Metadata } from "next"
import { getTranslations } from "next-intl/server"
import { LandingClient } from "@/components/landing/landing-client"

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "SkateLab — AI Тренер по фигурному катанию",
    description:
      "Запишите прыжок — увидьте миллиметры. AI-анализ техники: высота ЦМТ, доворот, время полёта. < 15 с на полный разбор видео.",
    alternates: { canonical: "https://skatelab.ru" },
    openGraph: {
      title: "SkateLab — AI Тренер по фигурному катанию",
      description: "Запишите прыжок — увидьте миллиметры. AI-анализ техники за < 15 секунд.",
      url: "https://skatelab.ru",
      siteName: "SkateLab",
      locale: "ru_RU",
      type: "website",
      images: [
        {
          url: "/images/og-image.png",
          width: 1200,
          height: 630,
          alt: "SkateLab — AI анализ фигурного катания",
        },
      ],
    },
  }
}

export default async function LandingPage() {
  const t = await getTranslations("landing")

  const faqItems = [
    { q: t("faqQ1"), a: t("faqA1") },
    { q: t("faqQ2"), a: t("faqA2") },
    { q: t("faqQ3"), a: t("faqA3") },
    { q: t("faqQ4"), a: t("faqA4") },
    { q: t("faqQ5"), a: t("faqA5") },
    { q: t("faqQ6"), a: t("faqA6") },
    { q: t("faqQ7"), a: t("faqA7") },
  ]

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
      logo: "https://skatelab.ru/images/og-image.png",
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
      <LandingClient />
    </>
  )
}
