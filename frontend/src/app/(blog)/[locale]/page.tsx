import { notFound, permanentRedirect } from "next/navigation"
import { isLocale } from "@/lib/docs-i18n"
import { blogUrl } from "@/lib/public-site"

export default async function LegacyBlog({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  if (!isLocale(locale)) notFound()
  permanentRedirect(blogUrl(locale))
}
