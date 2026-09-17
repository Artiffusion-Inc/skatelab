import { getLocale, getTranslations } from "next-intl/server"
import { ContactPage } from "@/components/landing/public-pages"
import { publicMetadata } from "@/lib/public-site"

export async function generateMetadata() {
  const t = await getTranslations("publicSite")
  return publicMetadata(t("contactTitle"), t("contactIntro"), "/contact", await getLocale())
}

export default ContactPage
