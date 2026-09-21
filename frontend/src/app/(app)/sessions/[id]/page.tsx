"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useMemo, useState } from "react"
import { AnalysisReadiness } from "@/components/analysis/analysis-readiness"
import { PhaseTimeline } from "@/components/analysis/phase-timeline"
import { SkeletonDetail } from "@/components/skeleton-detail"
import { VideoWithSkeleton } from "@/components/analysis/video-with-skeleton"
import { MetricRow } from "@/components/session/metric-row"
import { useLocale, useTranslations } from "@/i18n"
import {
  SESSION_POLLING_STATUSES,
  useSession,
  useDeleteSession,
  useRetrySession,
} from "@/lib/api/sessions"
import { useCancelProcess } from "@/lib/api/process"
import { useElementLabel, useMetricRegistry } from "@/hooks/use-metric-registry"
import { Button } from "@/components/ui/button"
import { FrameMetricsChart } from "@/components/analysis/frame-metrics-chart"
import { SessionDiagnostics } from "@/components/analysis/session-diagnostics"
import { ProcessingBanner } from "@/components/session/processing-banner"
import { SessionActionMenu } from "@/components/session/session-action-menu"
import { SessionDownloads } from "@/components/session/session-downloads"
import { useTabParam } from "@/hooks/use-tab-param"
import { AnalyzerTab } from "@/components/analysis/analyzer-tab"
import { CoachCommentForm } from "@/components/coach/coach-comment-form"
import { useAuth } from "@/components/auth-provider"
import { ErrorState } from "@/components/error-state"
import { ApiError } from "@/lib/api-client"

const POLLING_STATUSES = SESSION_POLLING_STATUSES
const SENSOR_METRIC_NAMES = new Set([
  "sensor_confidence",
  "rotation_symmetry",
  "imu_peak_delta",
  "landing_stability",
  "imu_offset_error",
  "imu_rate_error",
])
const SENSOR_METRIC_LABELS: Record<string, string> = {
  sensor_confidence: "Sensor confidence",
  rotation_symmetry: "Rotation symmetry",
  imu_peak_delta: "IMU peak delta",
  landing_stability: "Landing stability",
  imu_offset_error: "IMU offset error",
  imu_rate_error: "IMU rate error",
}

function isAxelElement(elementType: string): boolean {
  const normalized = elementType.toLowerCase()
  return normalized.includes("axel") || /^[1-4]a$/.test(normalized)
}

type ReportSession = NonNullable<ReturnType<typeof useSession>["data"]>

function SensorProvenance({ session, failed }: { session: ReportSession; failed: boolean }) {
  const t = useTranslations("session")
  const hasLeft = Boolean(session.imu_left_key)
  const hasRight = Boolean(session.imu_right_key)
  const hasManifest = Boolean(session.manifest_key)
  const diagnostics = session.metrics.filter(metric => SENSOR_METRIC_NAMES.has(metric.metric_name))
  const fused = !failed && hasLeft && hasRight && hasManifest

  return (
    <section
      className="rounded-2xl border border-hairline p-3 sm:p-4"
      aria-label={t("sensorTitle")}
    >
      <h2 className="mb-2 sh-button-cap text-ink">{t("sensorTitle")}</h2>
      <p className="text-sm sh-body-md" role="status">
        {fused ? t("sensorFusionSynthetic") : t("sensorFusionUnavailable")}
      </p>
      <p className="mt-1 text-xs text-ink-mute">
        {t("sensorSource", {
          left: hasLeft ? t("attached") : t("absent"),
          right: hasRight ? t("attached") : t("absent"),
          manifest: hasManifest ? t("attached") : t("absent"),
        })}
      </p>
      <p className="mt-1 text-xs text-ink-mute">{t("sensorValidation")}</p>
      {failed && session.error_message && (
        <p className="mt-2 text-xs text-destructive">
          {t("analysisError")}: {session.error_message}
        </p>
      )}
      {diagnostics.length > 0 && (
        <div className="mt-3 border-t border-hairline pt-3">
          <h3 className="mb-1 text-xs sh-button-cap text-ink">{t("measuredDiagnostics")}</h3>
          <dl className="space-y-1">
            {diagnostics.map(metric => {
              const decimals =
                metric.metric_name === "imu_rate_error"
                  ? 1
                  : metric.metric_name.includes("confidence") ||
                      metric.metric_name.includes("symmetry") ||
                      metric.metric_name.includes("stability")
                    ? 2
                    : 0
              return (
                <div key={metric.id} className="flex items-center justify-between text-xs">
                  <dt className="text-ink-mute">
                    {SENSOR_METRIC_LABELS[metric.metric_name] ?? metric.metric_name}
                  </dt>
                  <dd className="font-mono">
                    {metric.metric_value.toFixed(decimals)} {metric.unit ?? ""}
                  </dd>
                </div>
              )
            })}
          </dl>
        </div>
      )}
    </section>
  )
}

export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { data: session, isLoading, isError, error, refetch } = useSession(id)
  const { user } = useAuth()
  const elementLabel = useElementLabel()
  const ts = useTranslations("sessions")
  const tSession = useTranslations("session")
  const locale = useLocale()
  const { data: registry } = useMetricRegistry()
  const cancelMutation = useCancelProcess()
  const retryMutation = useRetrySession()
  const deleteMutation = useDeleteSession()
  const { activeTab, setTab } = useTabParam("overview")

  const isPolling = session ? POLLING_STATUSES.has(session.status) : false
  const isFailed = session?.status === "failed" || !!session?.error_message

  const [visitCount] = useState(() => {
    if (typeof window === "undefined") return 0
    const count = parseInt(localStorage.getItem("session_detail_visits") ?? "0", 10) + 1
    localStorage.setItem("session_detail_visits", String(count))
    return count
  })
  const [dismissed, setDismissed] = useState(false)

  const videoUrl = session?.processed_video_url ?? session?.video_url ?? null
  const hasVideo = Boolean(videoUrl)
  const poseData = session?.pose_data ?? null
  const hasPoseData = Boolean(poseData?.frames.length && poseData.poses.length)
  const totalFrames = hasPoseData && poseData ? Math.max(...poseData.frames) : 0

  // Overview: prioritize warnings and records, then show the first available values.
  const resultMetrics = useMemo(
    () => session?.metrics.filter(m => !SENSOR_METRIC_NAMES.has(m.metric_name)) ?? [],
    [session?.metrics],
  )
  const highlightMetrics = useMemo(() => {
    const highlighted = resultMetrics.filter(m => m.is_pr || m.is_in_range === false)
    return highlighted.length > 0 ? highlighted : resultMetrics.slice(0, 4)
  }, [resultMetrics])

  const handleShare = async () => {
    const url = typeof document !== "undefined" ? document.URL : ""
    await navigator.clipboard.writeText(url)
  }

  const handleDelete = () => {
    if (!session) return
    if (!window.confirm(tSession("deleteConfirm"))) return
    deleteMutation.mutate(session.id, {
      onSuccess: () => router.push("/feed"),
    })
  }

  if (isLoading) return <SkeletonDetail />

  if (isError) {
    const requiresAuth = error instanceof ApiError && error.status === 401
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <ErrorState
          title={requiresAuth ? tSession("sessionAuthError") : tSession("sessionLoadError")}
          message={
            requiresAuth ? tSession("sessionAuthErrorHint") : tSession("sessionLoadErrorHint")
          }
          onRetry={requiresAuth ? undefined : () => void refetch()}
        />
        {requiresAuth && (
          <div className="flex justify-center">
            <Button asChild>
              <Link href="/login">{tSession("signInAgain")}</Link>
            </Button>
          </div>
        )}
      </div>
    )
  }

  if (!session)
    return (
      <div className="flex flex-col items-center py-20 text-center" role="status">
        <p className="text-lg text-muted-foreground">{ts("notFound")}</p>
        <Link href="/feed" className="mt-4 text-sm text-primary hover:underline">
          {tSession("retry")}
        </Link>
      </div>
    )

  const elementType = session.element_type ?? "unknown"

  const tabs = [
    { key: "overview" as const, label: tSession("tabOverview") },
    { key: "details" as const, label: tSession("tabDetails") },
    { key: "analyzer" as const, label: tSession("tabAnalyzer") },
    { key: "export" as const, label: tSession("tabExport") },
  ]

  const handleRetry = () => {
    if (!session.video_key) return
    retryMutation.mutate({ sessionId: session.id, videoKey: session.video_key })
  }

  return (
    <>
      {/* Processing banner — replaces full-page SessionStatus */}
      {isPolling && (
        <ProcessingBanner
          taskId={session.process_task_id ?? null}
          onCancel={() => {
            if (session.process_task_id) {
              cancelMutation.mutate(session.process_task_id)
            }
          }}
          onRetry={handleRetry}
        />
      )}

      {/* Error banner — replaces full-page error state */}
      {isFailed && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-4 py-3" role="alert">
          <div className="mx-auto flex max-w-2xl items-center gap-3">
            <div className="flex-1">
              <p className="sh-button-cap text-destructive">{ts("analysisFailed")}</p>
              <p className="mt-0.5 text-xs text-ink-mute">{tSession("analysisFailedHint")}</p>
              {session.error_message && (
                <p className="mt-0.5 text-xs text-ink-mute">{session.error_message}</p>
              )}
              {retryMutation.isError && (
                <p className="mt-1 text-xs text-destructive">{tSession("retryError")}</p>
              )}
            </div>
            {session.video_key && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetry}
                disabled={retryMutation.isPending}
              >
                {retryMutation.isPending ? tSession("retrying") : tSession("retry")}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Header: element name + score + action menu */}
      <div className="mx-auto max-w-2xl px-4 pt-4 lg:max-w-none">
        <div className="relative flex items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">{elementLabel(elementType)}</h1>
            {visitCount === 1 && !dismissed && (
              <div className="absolute -bottom-8 left-0 whitespace-nowrap rounded-lg bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
                {tSession("tourTabs")}
                <button
                  type="button"
                  onClick={() => setDismissed(true)}
                  className="ml-2 opacity-70 hover:opacity-100"
                >
                  &times;
                </button>
              </div>
            )}
            <p className="text-sm text-ink-mute">
              {new Date(session.created_at).toLocaleDateString(locale)}
            </p>
            {session.overall_score !== null && (
              <p className="text-sm sh-button-cap" style={{ color: "var(--color-score-good)" }}>
                {/* #504/#507: backend emits overall_score as a 0..1 ratio
                 * (session_saver.py:94). The "из 10" label implies a 0..10
                 * scale, so scale x10 for display (1.0 → "10.0 из 10"), not
                 * the raw 0..1 ("1.0 из 10" reads as 10% deflation). */}
                {tSession("overallScore")}: {(session.overall_score * 10).toFixed(1)}{" "}
                {tSession("scoreOutOf")}
              </p>
            )}
          </div>
          <div className="relative">
            <SessionActionMenu
              sessionId={session.id}
              onDelete={handleDelete}
              onShare={handleShare}
            />
            {visitCount === 2 && !dismissed && (
              <div className="absolute -bottom-8 right-0 whitespace-nowrap rounded-lg bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
                {tSession("tourActions")}
                <button
                  type="button"
                  onClick={() => setDismissed(true)}
                  className="ml-2 opacity-70 hover:opacity-100"
                >
                  &times;
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="mx-auto max-w-2xl px-4 lg:max-w-none">
        <div className="flex gap-4 border-b border-hairline" role="tablist">
          {tabs.map(tab => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => setTab(tab.key)}
              className={`relative px-1 py-2.5 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
              {activeTab === tab.key && (
                <span className="absolute inset-x-0 -bottom-px h-0.5 bg-foreground" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab panels */}
      <div className="mx-auto max-w-2xl px-4 py-4 lg:max-w-none" role="tabpanel">
        {activeTab === "overview" && (
          <div className="space-y-6">
            <AnalysisReadiness
              hasVideo={hasVideo}
              hasPoseData={hasPoseData}
              metricCount={resultMetrics.length}
            />

            {/* Video hero */}
            {videoUrl && poseData && hasPoseData && (
              <VideoWithSkeleton
                videoUrl={videoUrl}
                poseData={poseData}
                phases={session.phases ?? null}
                totalFrames={totalFrames}
                fps={poseData.fps}
                className="rounded-xl"
              />
            )}
            {videoUrl && (!poseData || !hasPoseData) && (
              <video src={videoUrl} controls playsInline className="w-full rounded-xl">
                <track kind="captions" />
              </video>
            )}
            {!hasVideo && (
              <div className="rounded-2xl border border-hairline bg-muted/40 px-4 py-8 text-center">
                <p className="sh-heading-lg text-ink">{tSession("videoUnavailable")}</p>
                <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-ink-mute">
                  {tSession("videoUnavailableHint")}
                </p>
              </div>
            )}

            {/* Phase timeline */}
            {hasPoseData && <PhaseTimeline totalFrames={totalFrames} phases={session.phases} />}

            <SensorProvenance session={session} failed={isFailed} />

            {/* Recommendations */}
            {session.recommendations && session.recommendations.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 sh-button-cap text-ink">
                  {isAxelElement(elementType)
                    ? tSession("axelRecommendation")
                    : ts("recommendations")}
                </h2>
                <ul className="space-y-1 text-sm text-ink-mute">
                  {(isAxelElement(elementType)
                    ? session.recommendations.slice(0, 1)
                    : session.recommendations
                  ).map(r => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Coach feedback is available after the athlete's analysis is complete. */}
            {(session.status === "completed" || session.status === "done") &&
              user?.onboarding_role === "coach" && <CoachCommentForm sessionId={session.id} />}

            {resultMetrics.length === 0 && (
              <div className="rounded-2xl border border-hairline bg-muted/40 p-4">
                <h2 className="sh-button-cap text-ink">{tSession("metricsUnavailable")}</h2>
                <p className="mt-1 text-sm leading-6 text-ink-mute">
                  {tSession("metricsUnavailableHint")}
                </p>
              </div>
            )}

            {/* Key metrics — warnings and records first, then available values */}
            {highlightMetrics.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 text-sm font-medium">{ts("metrics")}</h2>
                {highlightMetrics.map(m => {
                  const def = registry?.[m.metric_name]
                  const label =
                    def?.label_ru ??
                    (
                      {
                        sensor_confidence: "Надёжность сенсоров",
                        rotation_symmetry: "Симметрия вращения",
                        imu_peak_delta: "Расхождение пиков IMU",
                        landing_stability: "Стабильность после приземления",
                        imu_offset_error: "Ошибка синхронизации IMU",
                        imu_rate_error: "Ошибка частоты IMU",
                      } as Record<string, string>
                    )[m.metric_name] ??
                    m.metric_name
                  const unit = def?.unit ?? m.unit ?? ""
                  const direction = def?.direction
                  return (
                    <MetricRow
                      key={m.id}
                      name={m.metric_name}
                      label={label}
                      value={m.metric_value}
                      unit={unit}
                      format={def?.format}
                      direction={direction}
                      isInRange={m.is_in_range}
                      isPr={m.is_pr}
                      prevBest={m.prev_best}
                      refRange={
                        m.reference_value ? [m.reference_value, m.reference_value + 1] : null
                      }
                    />
                  )
                })}
                {resultMetrics.length > highlightMetrics.length && (
                  <button
                    type="button"
                    onClick={() => setTab("details")}
                    className="mt-2 text-sm text-primary hover:underline"
                  >
                    {tSession("showAllMetrics")}
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === "details" && (
          <div className="space-y-6">
            {/* Frame metrics chart */}
            {poseData && hasPoseData && session.frame_metrics && (
              <FrameMetricsChart
                poseData={poseData}
                frameMetrics={session.frame_metrics}
                phases={session.phases ?? null}
                totalFrames={totalFrames}
              />
            )}

            {/* Synced phase timeline */}
            {hasPoseData && <PhaseTimeline totalFrames={totalFrames} phases={session.phases} />}

            <div className="rounded-2xl border border-hairline bg-muted/40 p-4">
              <h2 className="sh-button-cap text-ink">{tSession("threeDPanelTitle")}</h2>
              <p className="mt-1 text-sm leading-6 text-ink-mute">{tSession("threeDPanelHint")}</p>
            </div>

            {/* Full metrics table */}
            {session.metrics.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 text-sm font-medium">{ts("metrics")}</h2>
                {session.metrics
                  .filter(m => !SENSOR_METRIC_NAMES.has(m.metric_name))
                  .map(m => {
                    const def = registry?.[m.metric_name]
                    const label = def?.label_ru ?? m.metric_name
                    const unit = def?.unit ?? m.unit ?? ""
                    const direction = def?.direction
                    return (
                      <MetricRow
                        key={m.id}
                        name={m.metric_name}
                        label={label}
                        value={m.metric_value}
                        unit={unit}
                        format={def?.format}
                        direction={direction}
                        isInRange={m.is_in_range}
                        isPr={m.is_pr}
                        prevBest={m.prev_best}
                        refRange={
                          m.reference_value ? [m.reference_value, m.reference_value + 1] : null
                        }
                      />
                    )
                  })}
              </div>
            )}

            {/* Sensor diagnostics are shown with provenance and never as skating scores. */}
            <SensorProvenance session={session} failed={isFailed} />

            {/* Diagnostics */}
            <SessionDiagnostics elementType={elementType} />
          </div>
        )}

        {activeTab === "analyzer" && (
          <AnalyzerTab
            sessionId={session.id}
            // #539: totalFrames must be the MAX frame index (absolute), not
            // the sampled-count. worker.py:403 samples every 10 frames, so
            // frames.length=30 for a 300-frame video, but phase.start_frame
            // / end_frame are ABSOLUTE. Passing frames.length makes
            // PhaseTimelineExtended's percent math produce values ~10x too
            // large → phase zones render off-screen on every session.
            // Mirrors the correct pattern at line 61.
            totalFrames={totalFrames || 120}
          />
        )}

        {activeTab === "export" && (
          <div className="space-y-6">
            {/* Downloads */}
            <div className="rounded-2xl border border-hairline p-3 sm:p-4">
              <h2 className="mb-3 text-sm font-medium">{tSession("printReport")}</h2>
              <SessionDownloads
                videoUrl={session.processed_video_url ?? session.video_url}
                posesUrl={session.poses_url}
                csvUrl={session.csv_url}
              />
            </div>

            {/* Compare */}
            <div className="rounded-2xl border border-hairline p-3 sm:p-4">
              <h2 className="mb-3 text-sm font-medium">{tSession("compare")}</h2>
              <Button variant="outline" size="sm" asChild>
                <Link href={`/compare?left=${session.id}`}>{tSession("compare")}</Link>
              </Button>
            </div>

            {/* Print */}
            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-2 rounded-xl border border-hairline px-3 py-2 text-sm hover:bg-muted print:hidden"
            >
              {tSession("printReport")}
            </button>
          </div>
        )}
      </div>
    </>
  )
}
