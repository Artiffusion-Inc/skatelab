"use client"

import { FileVideo, Database, FileSpreadsheet } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

interface Props {
  videoUrl?: string | null
  posesUrl?: string | null
  csvUrl?: string | null
}

export function SessionDownloads({ videoUrl, posesUrl, csvUrl }: Props) {
  const t = useTranslations("download")

  const downloads = [
    { key: "video", url: videoUrl, label: t("video"), icon: FileVideo },
    { key: "poses", url: posesUrl, label: t("poses"), icon: Database },
    { key: "biomech", url: csvUrl, label: t("biomech"), icon: FileSpreadsheet },
  ]

  const available = downloads.filter(d => d.url)
  if (available.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {available.map(({ key, url, label, icon: Icon }) => (
        <Button key={key} variant="outline" size="sm" className="min-h-[44px]" asChild>
          <a href={url ?? "#"} download>
            <Icon className="mr-2 h-4 w-4" />
            {label}
          </a>
        </Button>
      ))}
    </div>
  )
}
