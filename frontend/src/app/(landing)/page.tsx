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
      <LandingClient />
    </>
  )
}
