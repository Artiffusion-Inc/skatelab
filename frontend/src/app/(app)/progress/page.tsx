"use client"

import { useState } from "react"
import { BarChart3, Upload } from "lucide-react"
import { PeriodSelector } from "@/components/progress/period-selector"
import { SkeletonChart } from "@/components/skeleton-chart"
import { ErrorState } from "@/components/error-state"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { TrendChart } from "@/components/progress/trend-chart"
import { EmptyState } from "@/components/onboarding"
import { useTranslations } from "@/i18n"
import { useMetricRegistry, useTrend } from "@/lib/api/metrics"
import { ELEMENT_TYPE_KEYS } from "@/lib/constants"

export default function ProgressPage() {
  const registryQuery = useMetricRegistry()
  const [element, setElement] = useState("waltz_jump")
  const [metric, setMetric] = useState("max_height")
  const [period, setPeriod] = useState("30d")
  const trendQuery = useTrend(undefined, element, metric, period)
  const { isFirstLoad, isError } = usePageStatus([registryQuery, trendQuery])
  const te = useTranslations("elements")
  const tEmpty = useTranslations("emptyStates")
  const ELEMENTS = ELEMENT_TYPE_KEYS.map(id => ({ id, label: te(id) }))

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

  if (isError) return <ErrorState onRetry={() => { registryQuery.refetch(); trendQuery.refetch() }} />

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

      <TrendChart data={trendQuery.data!} />
    </div>
  )
}
