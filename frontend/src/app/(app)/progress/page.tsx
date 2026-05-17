"use client"

import { Suspense, useState } from "react"
import { useSearchParams } from "next/navigation"
import { BarChart3 } from "lucide-react"
import { SkeletonChart } from "@/components/skeleton-chart"
import { ErrorState } from "@/components/error-state"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { MetricDeepDive } from "@/components/progress/metric-deep-dive"
import { EmptyState } from "@/components/onboarding"
import { useTranslations } from "@/i18n"
import { useDiagnostics } from "@/lib/api/metrics"
import { useConnections } from "@/lib/api/connections"
import { ELEMENT_TYPE_KEYS } from "@/lib/constants"
import { CoachViewSwitcher, type ViewMode } from "@/components/layout/coach-view-switcher"
import { ElementCard, type HealthStatus } from "@/components/progress/element-card"
import { ElementDetail } from "@/components/progress/element-detail"
import Link from "next/link"

function deriveHealth(
  findings: { severity: string; element: string }[],
  elementId: string,
): HealthStatus {
  const elementFindings = findings.filter(f => f.element === elementId)
  if (elementFindings.length === 0) return "no_data"
  if (elementFindings.some(f => f.severity === "warning")) return "declining"
  return "stagnant"
}

function ProgressContent() {
  const diagQuery = useDiagnostics()
  const connQuery = useConnections()
  const searchParams = useSearchParams()
  const elementParam = searchParams.get("element")
  const metricParam = searchParams.get("metric")
  const te = useTranslations("elements")
  const tEmpty = useTranslations("emptyStates")
  const tc = useTranslations("coach")
  const ts = useTranslations("students")

  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return "self"
    return (localStorage.getItem("coach_view_mode") as ViewMode) ?? "self"
  })

  const handleModeChange = (next: ViewMode) => {
    setViewMode(next)
    localStorage.setItem("coach_view_mode", next)
  }

  const students = (connQuery.data?.connections ?? []).filter(
    r => r.status === "active" && r.connection_type === "coaching",
  )
  const hasStudents = students.length > 0

  const { isFirstLoad, isError } = usePageStatus([diagQuery])

  // L2: metric deep dive when both element and metric are in the URL
  if (elementParam && metricParam) {
    return <MetricDeepDive elementId={elementParam} metricName={metricParam} />
  }

  // L1: element detail when element param is present
  if (
    elementParam &&
    ELEMENT_TYPE_KEYS.includes(elementParam as (typeof ELEMENT_TYPE_KEYS)[number])
  ) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
        {hasStudents && (
          <div className="flex justify-end">
            <CoachViewSwitcher mode={viewMode} onModeChange={handleModeChange} />
          </div>
        )}
        <ElementDetail
          elementId={elementParam}
          elementName={te(elementParam)}
          findings={diagQuery.data?.findings ?? []}
        />
      </div>
    )
  }

  if (isFirstLoad) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
        <SkeletonChart />
      </div>
    )
  }

  if (isError) {
    return (
      <ErrorState
        onRetry={() => {
          diagQuery.refetch()
        }}
      />
    )
  }

  // Students mode
  if (hasStudents && viewMode === "students") {
    return (
      <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
        <div className="flex items-center justify-between">
          <h1 className="sh-display-md">{tc("viewStudents")}</h1>
          <CoachViewSwitcher mode={viewMode} onModeChange={handleModeChange} />
        </div>
        <div className="space-y-2">
          {students.map(conn => (
            <Link
              key={conn.id}
              href={`/students/${conn.to_user_id}`}
              className="block rounded-2xl border border-border p-4 transition-colors hover:bg-accent/30"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-sm font-medium">
                  {(conn.to_user_name ?? "?")[0].toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-medium">
                    {conn.to_user_name ?? tc("studentFallback")}
                  </p>
                  <p className="text-xs text-muted-foreground">{ts("progress")}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    )
  }

  // L0: element cards grid
  const findings = diagQuery.data?.findings ?? []

  if (findings.length === 0 && !diagQuery.data) {
    return (
      <EmptyState
        icon={<BarChart3 className="h-7 w-7 text-primary" />}
        title={tEmpty("progressTitle")}
        description={tEmpty("progressDesc")}
        primaryAction={{ label: tEmpty("progressAction"), href: "/upload" }}
      />
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
      {hasStudents && (
        <div className="flex justify-end">
          <CoachViewSwitcher mode={viewMode} onModeChange={handleModeChange} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {ELEMENT_TYPE_KEYS.map(id => (
          <ElementCard
            key={id}
            elementId={id}
            health={deriveHealth(findings, id)}
            findingCount={findings.filter(f => f.element === id).length}
          />
        ))}
      </div>
    </div>
  )
}

export default function ProgressPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
          <SkeletonChart />
        </div>
      }
    >
      <ProgressContent />
    </Suspense>
  )
}
