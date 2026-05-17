"use client"

import { useState } from "react"
import { BarChart3 } from "lucide-react"
import { PeriodSelector } from "@/components/progress/period-selector"
import { SkeletonChart } from "@/components/skeleton-chart"
import { ErrorState } from "@/components/error-state"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { TrendChart } from "@/components/progress/trend-chart"
import { EmptyState } from "@/components/onboarding"
import { useTranslations } from "@/i18n"
import { useMetricRegistry, useTrend } from "@/lib/api/metrics"
import { useConnections } from "@/lib/api/connections"
import { ELEMENT_TYPE_KEYS } from "@/lib/constants"
import { CoachViewSwitcher, type ViewMode } from "@/components/layout/coach-view-switcher"
import Link from "next/link"

export default function ProgressPage() {
  const registryQuery = useMetricRegistry()
  const connQuery = useConnections()
  const [element, setElement] = useState("waltz_jump")
  const [metric, setMetric] = useState("max_height")
  const [period, setPeriod] = useState("30d")
  const trendQuery = useTrend(undefined, element, metric, period)
  const { isFirstLoad, isError } = usePageStatus([registryQuery, trendQuery])
  const te = useTranslations("elements")
  const tEmpty = useTranslations("emptyStates")
  const tc = useTranslations("coach")
  const ts = useTranslations("students")
  const ELEMENTS = ELEMENT_TYPE_KEYS.map(id => ({ id, label: te(id) }))

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

  const availableMetrics = registryQuery.data
    ? Object.entries(registryQuery.data).filter(([, v]) => v.element_types.includes(element))
    : []

  if (isFirstLoad) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
        <SkeletonChart />
      </div>
    )
  }

  if (isError)
    return (
      <ErrorState
        onRetry={() => {
          registryQuery.refetch()
          trendQuery.refetch()
        }}
      />
    )

  // Students mode: show student list with links
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
              className="block rounded-2xl border border-border p-4 hover:bg-accent/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
                  {(conn.to_user_name ?? "?")[0].toUpperCase()}
                </div>
                <div>
                  <p className="font-medium text-sm">
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

  // Self mode: show trend chart (original content)
  if (!trendQuery.data || trendQuery.data.data_points.length === 0) {
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

      <div className="grid grid-cols-4 gap-1.5 sm:gap-2">
        {ELEMENTS.map(el => (
          <button
            type="button"
            key={el.id}
            onClick={() => setElement(el.id)}
            className={`truncate rounded-xl border p-1.5 text-center text-[11px] sm:p-2 sm:text-xs ${element === el.id ? "border-primary bg-primary/10" : "border-hairline"}`}
          >
            {el.label}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        <select
          value={metric}
          onChange={e => setMetric(e.target.value)}
          className="w-full rounded-xl border border-hairline bg-background px-3 py-2.5 text-sm"
        >
          {availableMetrics.map(([name, def]) => (
            <option key={name} value={name}>
              {def.label_ru}
            </option>
          ))}
        </select>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      <TrendChart data={trendQuery.data as NonNullable<typeof trendQuery.data>} />
    </div>
  )
}
