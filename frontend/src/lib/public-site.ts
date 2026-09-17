import type { Metadata } from "next"
import type { Locale } from "@/lib/docs-i18n"

export const TELEGRAM_URL = "https://t.me/xpos587"
export const PUBLIC_ROUTES = [
  "/",
  "/how-it-works",
  "/equipment",
  "/contact",
  "/blog",
  "/tiktok",
  "/privacy",
  "/terms",
  "/offer",
  "/cookies",
] as const

export function blogUrl(locale: Locale, slugs: string[] = []): string {
  return ["", "blog", locale, ...slugs].join("/")
}

export function publicMetadata(
  title: string,
  description: string,
  path: string,
  locale = "ru",
  image = "hero-rink",
): Metadata {
  const url = `https://skatelab.ru${path}`
  const images = [`https://skatelab.ru/images/landing/${image}.webp`]
  return {
    title: `${title} — SkateLab`,
    description,
    alternates: { canonical: url },
    openGraph: {
      title,
      description,
      url,
      siteName: "SkateLab",
      locale: locale === "en" ? "en_US" : "ru_RU",
      type: "website",
      images,
    },
    twitter: { card: "summary_large_image", title, description, images },
  }
}
