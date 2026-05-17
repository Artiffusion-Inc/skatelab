import Link from "next/link"
import { Upload } from "lucide-react"
import { useTranslations } from "@/i18n"

export function UploadCtaBanner() {
  const t = useTranslations("demo")
  return (
    <div className="sticky top-0 z-30 border-b border-primary/20 bg-primary/5 px-4 py-2.5">
      <Link
        href="/upload"
        className="mx-auto flex max-w-2xl items-center justify-center gap-2 text-sm font-medium text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <Upload className="h-4 w-4" />
        {t("uploadCta")}
      </Link>
    </div>
  )
}
