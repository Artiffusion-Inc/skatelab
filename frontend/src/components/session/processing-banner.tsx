"use client"

import { useProcessStream } from "@/hooks/use-process-stream"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"

interface ProcessingBannerProps {
  taskId: string | null
  onCancel: () => void
}

export function ProcessingBanner({ taskId, onCancel }: ProcessingBannerProps) {
  const stream = useProcessStream(taskId)
  const t = useTranslations("session")

  if (!taskId) return null

  const progress = stream.state?.progress ?? 0
  const status = stream.state?.status ?? "queued"

  return (
    <div
      className="sticky top-0 z-40 border-b border-primary/20 bg-primary/5 px-4 py-3"
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium">
            {status === "queued" ? t("queued") : t("analyzing")}
          </p>
          <Progress value={progress} className="h-1.5" />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          className="shrink-0 text-sm text-ink-mute"
        >
          {t("cancel")}
        </Button>
      </div>
    </div>
  )
}
