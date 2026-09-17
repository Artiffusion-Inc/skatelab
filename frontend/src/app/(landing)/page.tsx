import type { Metadata } from "next"
import { getTranslations } from "next-intl/server"
import { LandingClient } from "@/components/landing/landing-client"

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "SkateLab — точный разбор техники для школы",
    description:
      "Видео, данные с оборудования и рабочий контур тренера для школ фигурного катания. Обсудите пилот со SkateLab.",
    alternates: { canonical: "https://skatelab.ru" },
    openGraph: {
      title: "SkateLab — точный разбор техники для школы",
      description:
        "Видео, данные с оборудования и рабочий контур тренера для школ фигурного катания. Обсудите пилот со SkateLab.",
      url: "https://skatelab.ru",
      siteName: "SkateLab",
      locale: "ru_RU",
      type: "website",
      images: [
        {
          url: "https://skatelab.ru/images/landing/hero-rink.webp",
          width: 1600,
          height: 900,
          alt: "Фигурист на тренировке",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "SkateLab — точный разбор техники для школы",
      description:
        "Видео, данные с оборудования и рабочий контур тренера для школ фигурного катания. Обсудите пилот со SkateLab.",
      images: ["https://skatelab.ru/images/landing/hero-rink.webp"],
    },
  }
}

export default async function LandingPage() {
  const t = await getTranslations("landing")
  const faqItems = [1, 2, 3].map(n => ({
    q: t(`question${n}`),
    a: t(`answer${n}`),
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
