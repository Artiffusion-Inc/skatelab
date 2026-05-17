"use client"

import { useQuery } from "@tanstack/react-query"
import { DemoBadge } from "@/components/demo/demo-badge"
import { UploadCtaBanner } from "@/components/demo/upload-cta-banner"
import { SkeletonDetail } from "@/components/skeleton-detail"
import { MetricRow } from "@/components/session/metric-row"
import { useTranslations } from "@/i18n"

interface DemoMetric {
  id: string
  metric_name: string
  metric_value: number
  unit: string
  is_in_range: boolean | null
  is_pr: boolean
  prev_best: number | null
  reference_value: number | null
}

interface DemoSession {
  id: string
  element_type: string
  status: string
  overall_score: number
  created_at: string
  metrics: DemoMetric[]
  recommendations: string[]
  is_demo: boolean
}

export default function DemoSessionPage() {
  const te = useTranslations("elements")
  const ts = useTranslations("sessions")
  const tSession = useTranslations("session")

  const { data: demo, isLoading } = useQuery({
    queryKey: ["demo-session"],
    queryFn: () => fetch("/demo/session.json").then(r => r.json() as Promise<DemoSession>),
  })

  if (isLoading || !demo) return <SkeletonDetail />

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <UploadCtaBanner />
      <div className="space-y-4 px-4 pt-4">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold">{te(demo.element_type)}</h1>
          <DemoBadge />
        </div>
        <p className="text-sm text-ink-mute">
          {new Date(demo.created_at).toLocaleDateString("ru-RU")}
        </p>
        {demo.overall_score !== null && (
          <p className="text-sm font-medium" style={{ color: "oklch(var(--score-good))" }}>
            {tSession("overallScore")}: {demo.overall_score.toFixed(1)} {tSession("scoreOutOf")}
          </p>
        )}

        {demo.metrics.length > 0 && (
          <div className="rounded-2xl border border-hairline p-3 sm:p-4">
            <h2 className="mb-2 text-sm font-medium">{ts("metrics")}</h2>
            {demo.metrics.map(m => (
              <MetricRow
                key={m.id}
                name={m.metric_name}
                label={m.metric_name}
                value={m.metric_value}
                unit={m.unit}
                direction={undefined}
                isInRange={m.is_in_range}
                isPr={m.is_pr}
                prevBest={m.prev_best}
                refRange={null}
              />
            ))}
          </div>
        )}

        {demo.recommendations.length > 0 && (
          <div className="rounded-2xl border border-hairline p-3 sm:p-4">
            <h2 className="mb-2 text-sm font-medium">{ts("recommendations")}</h2>
            <ul className="space-y-1 text-sm text-ink-mute">
              {demo.recommendations.map(r => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
