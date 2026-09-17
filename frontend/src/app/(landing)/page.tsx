import type { Metadata } from "next"
import { getLocale, getTranslations } from "next-intl/server"
import { publicMetadata } from "@/lib/public-site"
import { LandingClient } from "@/components/landing/landing-client"

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("landing")
  return publicMetadata(t("heroTitle"), t("heroLead"), "/", await getLocale())
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
