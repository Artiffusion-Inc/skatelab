import { getTranslations } from "next-intl/server"

export async function PlaceholderPage({ title }: { title: string }) {
  const t = await getTranslations("placeholder")
  return (
    <div className="mx-auto max-w-4xl p-6">
      <h2 className="sh-heading-lg mb-4">{title}</h2>
      <p className="text-ink-mute">{t("inDevelopment")}</p>
    </div>
  )
}
