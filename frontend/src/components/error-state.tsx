"use client"

import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
}

export function ErrorState({ title, message, onRetry }: ErrorStateProps) {
  const t = useTranslations("errorState")

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12 text-center" role="alert">
      <AlertTriangle className="h-10 w-10 text-muted-foreground" />
      <div>
        <h3 className="text-lg font-medium">{title ?? t("title")}</h3>
        {message && <p className="mt-1 text-sm text-muted-foreground">{message}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          {t("retry")}
        </Button>
      )}
    </div>
  )
}
