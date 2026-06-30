"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { lazy, Suspense, useMemo, useState } from "react"
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

const ThreeJSkeletonViewer = lazy(() =>
  import("@/components/analysis/threejs-skeleton-viewer").then(m => ({
    default: m.ThreeJSkeletonViewer,
  })),
)

const POLLING_STATUSES = SESSION_POLLING_STATUSES

export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { data: session, isLoading } = useSession(id)
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

  const totalFrames = session?.pose_data ? Math.max(...session.pose_data.frames) : 300

  // Overview tab: show only out-of-range + PRs
  const highlightMetrics = useMemo(() => {
    if (!session?.metrics) return []
    return session.metrics.filter(m => m.is_pr || m.is_in_range === false)
  }, [session?.metrics])

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
  if (!session)
    return (
      <div className="flex flex-col items-center py-20 text-center" role="status">
        <p className="text-lg text-muted-foreground">{ts("notFound")}</p>
        <Link href="/feed" className="mt-4 text-sm text-primary hover:underline">
          {tSession("retry")}
        </Link>
      </div>
    )

  const tabs = [
    { key: "overview" as const, label: tSession("tabOverview") },
    { key: "details" as const, label: tSession("tabDetails") },
    { key: "analyzer" as const, label: tSession("tabAnalyzer") },
    { key: "export" as const, label: tSession("tabExport") },
  ]

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
          onRetry={() => {
            if (session.video_key) {
              retryMutation.mutate({
                sessionId: session.id,
                videoKey: session.video_key as string,
              })
            }
          }}
        />
      )}

      {/* Error banner — replaces full-page error state */}
      {isFailed && (
        <div className="border-b border-destructive/20 bg-destructive/5 px-4 py-3" role="alert">
          <div className="mx-auto flex max-w-2xl items-center gap-3">
            <div className="flex-1">
              <p className="text-sm font-medium text-destructive">{ts("analysisFailed")}</p>
              {session.error_message && (
                <p className="mt-0.5 text-xs text-ink-mute">{session.error_message}</p>
              )}
            </div>
            {session.video_key && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  retryMutation.mutate({
                    sessionId: session.id,
                    videoKey: session.video_key as string,
                  })
                }
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
            <h1 className="text-xl font-semibold">{elementLabel(session.element_type)}</h1>
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
              <p className="text-sm font-medium" style={{ color: "oklch(var(--score-good))" }}>
                {tSession("overallScore")}: {session.overall_score.toFixed(1)}{" "}
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
            {/* Video hero */}
            {session.processed_video_url && session.pose_data && (
              <VideoWithSkeleton
                videoUrl={session.processed_video_url}
                poseData={session.pose_data}
                phases={session.phases ?? null}
                totalFrames={totalFrames}
                fps={session.pose_data.fps}
                className="rounded-xl"
              />
            )}
            {session.processed_video_url && !session.pose_data && (
              <video src={session.processed_video_url} controls className="w-full rounded-xl">
                <track kind="captions" />
              </video>
            )}
            {!session.processed_video_url && session.video_url && (
              <video src={session.video_url} controls className="w-full rounded-xl">
                <track kind="captions" />
              </video>
            )}

            {/* Phase timeline */}
            {session.pose_data && (
              <PhaseTimeline totalFrames={totalFrames} phases={session.phases} />
            )}

            {/* Recommendations */}
            {session.recommendations && session.recommendations.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 text-sm font-medium">{ts("recommendations")}</h2>
                <ul className="space-y-1 text-sm text-ink-mute">
                  {session.recommendations.map(r => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Key metrics — out-of-range + PRs only */}
            {highlightMetrics.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 text-sm font-medium">{ts("metrics")}</h2>
                {highlightMetrics.map(m => {
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
                {session.metrics.length > highlightMetrics.length && (
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
            {session.pose_data && session.frame_metrics && (
              <FrameMetricsChart
                poseData={session.pose_data}
                frameMetrics={session.frame_metrics}
                phases={session.phases ?? null}
                totalFrames={totalFrames}
              />
            )}

            {/* Synced phase timeline */}
            {session.pose_data && (
              <PhaseTimeline totalFrames={totalFrames} phases={session.phases} />
            )}

            {/* 3D viewer — only mounted when details tab is active */}
            {session.pose_data && session.frame_metrics && (
              <div className="relative">
                <Suspense
                  fallback={<div className="aspect-square animate-pulse rounded-xl bg-muted" />}
                >
                  <ThreeJSkeletonViewer
                    poseData={session.pose_data}
                    frameMetrics={session.frame_metrics}
                    className="rounded-xl"
                  />
                </Suspense>
                {visitCount === 3 && !dismissed && (
                  <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
                    {tSession("tour3d")}
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
            )}

            {/* Full metrics table */}
            {session.metrics.length > 0 && (
              <div className="rounded-2xl border border-hairline p-3 sm:p-4">
                <h2 className="mb-2 text-sm font-medium">{ts("metrics")}</h2>
                {session.metrics.map(m => {
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

            {/* Diagnostics */}
            {session.pose_data && <SessionDiagnostics elementType={session.element_type} />}
          </div>
        )}

        {activeTab === "analyzer" && (
          <AnalyzerTab
            sessionId={session.id}
            totalFrames={session.pose_data?.frames?.length ?? 120}
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
