import { getLocale, getTranslations } from "next-intl/server"
import { ProcessPage } from "@/components/landing/public-pages"
import { publicMetadata } from "@/lib/public-site"

export async function generateMetadata() {
  const t = await getTranslations("publicSite")
  return publicMetadata(t("processTitle"), t("processIntro"), "/how-it-works", await getLocale())
}

export default ProcessPage
