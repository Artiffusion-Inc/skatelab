"use client"

import { BarChart3, Check, FlaskConical, Layers3, Video, VideoOff, X } from "lucide-react"
import { useTranslations } from "@/i18n"

export type AnalysisPart = "video" | "pose" | "metrics"

interface AnalysisAvailabilityInput {
  hasVideo: boolean
  hasPoseData: boolean
  metricCount: number
}

export function getAnalysisAvailability({
  hasVideo,
  hasPoseData,
  metricCount,
}: AnalysisAvailabilityInput): { missing: AnalysisPart[]; has3d: false } {
  const missing: AnalysisPart[] = []
  if (!hasVideo) missing.push("video")
  if (!hasPoseData) missing.push("pose")
  if (metricCount === 0) missing.push("metrics")
  return { missing, has3d: false }
}

interface AnalysisReadinessProps extends AnalysisAvailabilityInput {
  className?: string
}

export function AnalysisReadiness({
  hasVideo,
  hasPoseData,
  metricCount,
  className = "",
}: AnalysisReadinessProps) {
  const t = useTranslations("analysis")
  const availability = getAnalysisAvailability({ hasVideo, hasPoseData, metricCount })
  const parts = [
    { key: "video", label: t("videoLayer"), ready: hasVideo, Icon: Video },
    { key: "pose", label: t("poseLayer"), ready: hasPoseData, Icon: Layers3 },
    { key: "metrics", label: t("metricsLayer"), ready: metricCount > 0, Icon: BarChart3 },
  ] as const

  return (
    <section
      className={`rounded-2xl border border-primary/20 bg-primary/5 p-4 sm:p-5 ${className}`}
      aria-labelledby="analysis-readiness-title"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <FlaskConical className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 id="analysis-readiness-title" className="sh-heading-lg text-ink">
            {t("experimentalTitle")}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-mute">
            {t("experimentalDescription")}
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3" aria-live="polite">
        {parts.map(({ key, label, ready, Icon }) => (
          <div
            key={key}
            className={`flex min-h-11 items-center gap-2 rounded-xl border border-hairline px-3 py-2 text-sm ${
              ready ? "bg-background text-ink" : "bg-background text-ink-mute"
            }`}
            style={{
              borderColor: ready
                ? "color-mix(in oklch, var(--color-score-good) 30%, transparent)"
                : "color-mix(in oklch, var(--color-score-mid) 40%, transparent)",
            }}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">{label}</span>
            {ready ? (
              <Check
                className="h-4 w-4 shrink-0"
                style={{ color: "var(--color-score-good)" }}
                aria-label={t("available")}
              />
            ) : (
              <X
                className="h-4 w-4 shrink-0"
                style={{ color: "var(--color-score-mid)" }}
                aria-label={t("unavailable")}
              />
            )}
            <span className="sh-micro whitespace-nowrap text-ink-mute">
              — {ready ? t("available") : t("unavailable")}
            </span>
          </div>
        ))}
      </div>

      {availability.missing.length > 0 && (
        <div
          className="mt-3 flex items-start gap-2 rounded-xl border bg-background px-3 py-2.5 text-sm text-ink-mute"
          style={{ borderColor: "color-mix(in oklch, var(--color-score-mid) 30%, transparent)" }}
        >
          <VideoOff
            className="mt-0.5 h-4 w-4 shrink-0"
            style={{ color: "var(--color-score-mid)" }}
            aria-hidden="true"
          />
          <p>
            <strong className="sh-button-cap text-ink">{t("partialResultTitle")}</strong>{" "}
            {t("partialResultDescription")}
          </p>
        </div>
      )}

      <div className="mt-3 flex items-start gap-2 border-t border-primary/15 pt-3 text-sm text-ink-mute">
        <Layers3 className="mt-0.5 h-4 w-4 shrink-0 text-ink-mute" aria-hidden="true" />
        <p>
          <strong className="sh-button-cap text-ink">{t("threeDUnavailable")}</strong>{" "}
          {t("threeDUnavailableDescription")}
        </p>
      </div>
    </section>
  )
}
