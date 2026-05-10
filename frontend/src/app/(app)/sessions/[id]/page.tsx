"use client"

import { useParams } from "next/navigation"
import { lazy, Suspense } from "react"
import { PhaseTimeline } from "@/components/analysis/phase-timeline"
import { SkeletonDetail } from "@/components/skeleton-detail"
import { VideoWithSkeleton } from "@/components/analysis/video-with-skeleton"
import { MetricRow } from "@/components/session/metric-row"
import { SessionStatus } from "@/components/session/session-status"
import { useTranslations } from "@/i18n"
import { useSession } from "@/lib/api/sessions"
import { useCancelProcess } from "@/lib/api/process"
import { useMetricRegistry } from "@/hooks/use-metric-registry"
import { useProcessStream } from "@/hooks/use-process-stream"
import { useRetrySession } from "@/lib/api/sessions"
import { Button } from "@/components/ui/button"
import { Printer } from "lucide-react"
import { FrameMetricsChart } from "@/components/analysis/frame-metrics-chart"
import { SessionActions } from "@/components/session/session-actions"
import { SessionDownloads } from "@/components/session/session-downloads"
import { SessionDiagnostics } from "@/components/analysis/session-diagnostics"

const ThreeJSkeletonViewer = lazy(() =>
  import("@/components/analysis/threejs-skeleton-viewer").then(m => ({
    default: m.ThreeJSkeletonViewer,
  })),
)

const POLLING_STATUSES = new Set(["queued", "uploading", "running", "pending"])

export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: session, isLoading } = useSession(id, {
    refetchInterval: query => {
      const status = query.state.data?.status
      return POLLING_STATUSES.has(status ?? "") ? 3000 : false
    },
  })
  const te = useTranslations("elements")
  const ts = useTranslations("sessions")
  const tSession = useTranslations("session")
  const { data: registry } = useMetricRegistry()
  const cancelMutation = useCancelProcess()

  const processStream = useProcessStream(session?.process_task_id ?? null)
  const retryMutation = useRetrySession()

  const totalFrames = session?.pose_data ? Math.max(...session.pose_data.frames) : 300

  if (isLoading) return <SkeletonDetail />
  if (!session) return <div className="py-20 text-center text-ink-mute">{ts("notFound")}</div>

  if (POLLING_STATUSES.has(session.status)) {
    return (
      <SessionStatus
        status={session.status}
        progress={processStream.state?.progress}
        onCancel={() => {
          if (session.process_task_id) {
            cancelMutation.mutate(session.process_task_id)
          }
        }}
      />
    )
  }

  if (session.status === "failed" || session.error_message) {
    return (
      <div className="mx-auto max-w-lg space-y-4 px-4 py-20 text-center">
        <p className="sh-display-md text-destructive">{ts("analysisFailed")}</p>
        <p className="text-sm text-ink-mute">{session.error_message}</p>
        {session.video_key && (
          <Button
            onClick={() =>
              retryMutation.mutate({ sessionId: session.id, videoKey: session.video_key as string })
            }
            disabled={retryMutation.isPending}
          >
            {retryMutation.isPending ? tSession("retrying") : tSession("retry")}
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 lg:max-w-none lg:grid lg:grid-cols-2 lg:gap-6">
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">
            {te(session.element_type) ?? session.element_type}
          </h1>
          <p className="text-sm text-ink-mute">
            {new Date(session.created_at).toLocaleDateString("ru-RU")}
          </p>
          {session.overall_score !== null && (
            <p className="text-sm font-medium" style={{ color: "oklch(var(--score-good))" }}>
              {tSession("overallScore")}: {session.overall_score.toFixed(1)}{" "}
              {tSession("scoreOutOf")}
            </p>
          )}
        </div>

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

        {session.pose_data && (
          <PhaseTimeline totalFrames={totalFrames} phases={session.phases ?? {}} />
        )}

        {session.pose_data && session.frame_metrics && (
          <FrameMetricsChart
            poseData={session.pose_data}
            frameMetrics={session.frame_metrics}
            phases={session.phases ?? null}
            totalFrames={totalFrames}
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
      </div>

      <div className="space-y-6">
        <SessionActions sessionId={session.id} />

        {session.pose_data && session.frame_metrics && (
          <Suspense fallback={<div className="aspect-square rounded-xl bg-muted animate-pulse" />}>
            <ThreeJSkeletonViewer
              poseData={session.pose_data}
              frameMetrics={session.frame_metrics}
              className="rounded-xl"
            />
          </Suspense>
        )}

        {session.metrics.length > 0 && (
          <div className="rounded-2xl border border-hairline p-3 sm:p-4">
            <h2 className="text-sm font-medium mb-2">{ts("metrics")}</h2>
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
                  refRange={m.reference_value ? [m.reference_value, m.reference_value + 1] : null}
                />
              )
            })}
          </div>
        )}

        {session.recommendations && session.recommendations.length > 0 && (
          <div className="rounded-2xl border border-hairline p-3 sm:p-4">
            <h2 className="text-sm font-medium mb-2">{ts("recommendations")}</h2>
            <ul className="space-y-1 text-sm text-ink-mute">
              {session.recommendations.map(r => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {session.pose_data && <SessionDiagnostics elementType={session.element_type} />}

        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center gap-2 rounded-xl border border-hairline px-3 py-2 text-sm hover:bg-muted print:hidden"
        >
          <Printer className="h-4 w-4" />
          {tSession("printReport")}
        </button>

        <SessionDownloads
          videoUrl={session.processed_video_url ?? session.video_url}
          posesUrl={session.poses_url}
          csvUrl={session.csv_url}
        />
      </div>
    </div>
  )
}
