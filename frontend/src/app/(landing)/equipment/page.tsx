import { getLocale, getTranslations } from "next-intl/server"
import { EquipmentPage } from "@/components/landing/public-pages"
import { publicMetadata } from "@/lib/public-site"

export async function generateMetadata() {
  const t = await getTranslations("publicSite")
  return publicMetadata(t("equipmentTitle"), t("equipmentIntro"), "/equipment", await getLocale())
}

export default EquipmentPage
