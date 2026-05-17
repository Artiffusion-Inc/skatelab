"use client"

import { Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

interface Props {
  status: string
  progress?: number
  onCancel?: () => void
}

export function SessionStatus({ status: _status, progress, onCancel }: Props) {
  const t = useTranslations("session")

  return (
    <div className="flex flex-col items-center justify-center gap-4 px-4 py-20">
      <Loader2 className="h-10 w-10 animate-spin text-primary" />
      <p className="sh-display-md">{t("analyzing")}</p>
      {progress !== undefined && progress > 0 && (
        <p className="text-sm text-ink-mute">{progress}%</p>
      )}
      {onCancel && (
        <Button variant="outline" size="sm" onClick={onCancel} className="min-h-[44px]">
          <X className="mr-2 h-4 w-4" />
          {t("cancel")}
        </Button>
      )}
    </div>
  )
}
