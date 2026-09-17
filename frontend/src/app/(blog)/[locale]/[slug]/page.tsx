import { notFound, permanentRedirect } from "next/navigation"
import { isLocale } from "@/lib/docs-i18n"
import { blogUrl } from "@/lib/public-site"
import { blog } from "@/lib/blog-source"

export default async function LegacyArticle({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>
}) {
  const { locale, slug } = await params
  if (!isLocale(locale) || !blog.getPage([slug], locale)) notFound()
  permanentRedirect(blogUrl(locale, [slug]))
}
