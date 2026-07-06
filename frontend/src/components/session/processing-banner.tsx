"use client"

import { useRef, useState } from "react"
import { useProcessStream } from "@/hooks/use-process-stream"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { useTranslations } from "@/i18n"
import { useMountEffect } from "@/lib/useMountEffect"

interface ProcessingBannerProps {
  taskId: string | null
  onCancel: () => void
  onRetry?: () => void
}

export function ProcessingBanner({ taskId, onCancel, onRetry }: ProcessingBannerProps) {
  const stream = useProcessStream(taskId)
  const t = useTranslations("session")

  const mountTime = useRef(Date.now())
  const [now, setNow] = useState(Date.now())

  useMountEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000)
    return () => clearInterval(id)
  })

  if (!taskId) return null

  // #831: backend worker emits progress in 0..1 (0.0, 0.1, 0.7, 1.0), but
  // <Progress> computes `translateX(-${100 - value}%)` expecting 0..100. A
  // raw 0.7 rendered at 99.3% (≈full) and terminal 1.0 never reached 100%.
  // Normalize here so the indicator reflects real percentage.
  const rawProgress = stream.state?.progress ?? 0
  const progress = Math.min(Math.round(rawProgress * 100), 100)
  const status = stream.state?.status ?? "queued"

  const elapsed = (now - mountTime.current) / 1000
  const isSlow = elapsed > 180 // 3 min
  const isStale = elapsed > 600 // 10 min

  const staleColor = isStale ? "border-warning/30 bg-warning/5" : "border-primary/20 bg-primary/5"

  return (
    <div
      className={`sticky top-0 z-40 border-b px-4 py-3 ${staleColor}`}
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium">
            {status === "queued" ? t("queued") : t("analyzing")}
          </p>
          <Progress value={progress} className="h-1.5" />
          {isStale && <p className="text-xs font-medium text-warning">{t("staleAnalysis")}</p>}
          {isSlow && !isStale && <p className="text-xs text-ink-mute">{t("slowAnalysis")}</p>}
        </div>
        {isStale && onRetry && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            className="shrink-0 text-sm min-h-[44px]"
          >
            {t("retry")}
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          className="shrink-0 text-sm text-ink-mute min-h-[44px]"
        >
          {t("cancel")}
        </Button>
      </div>
    </div>
  )
}
