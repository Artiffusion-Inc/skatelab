import { useTranslations } from "@/i18n"

export function DemoBadge() {
  const t = useTranslations("demo")
  return (
    <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
      {t("badge")}
    </span>
  )
}
