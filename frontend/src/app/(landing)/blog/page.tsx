import { getLocale } from "next-intl/server"
import { redirect } from "next/navigation"
import { blogUrl } from "@/lib/public-site"
import { resolveLocale } from "@/lib/docs-i18n"

export default async function BlogIndex() {
  redirect(blogUrl(resolveLocale(await getLocale())))
}
