"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft, ChevronDown } from "lucide-react"
import { useTranslations } from "@/i18n"
import { useMetricRegistry, useTrend, usePRs } from "@/lib/api/metrics"
import { TrendChart } from "@/components/progress/trend-chart"
import { PeriodSelector } from "@/components/progress/period-selector"
import { MetricCard } from "@/components/progress/metric-card"
import type { DiagnosticsFinding } from "@/types"

interface ElementDetailProps {
  elementId: string
  elementName: string
  findings: DiagnosticsFinding[]
}

export function ElementDetail({ elementId, elementName, findings }: ElementDetailProps) {
  const router = useRouter()
  const tp = useTranslations("progress")
  const tc = useTranslations("common")
  const [period, setPeriod] = useState("30d")
  const [showAllMetrics, setShowAllMetrics] = useState(false)

  const { data: registry } = useMetricRegistry()
  const { data: prData } = usePRs(undefined, elementId)

  // Element-specific findings (top 3 for alerts)
  const elementFindings = findings.filter(f => f.element === elementId)
  const topAlerts = elementFindings.slice(0, 3)

  // Metrics available for this element
  const allMetrics = registry
    ? Object.entries(registry).filter(([, v]) => v.element_types.includes(elementId))
    : []

  // Primary metric for the trend chart = first available metric
  const primaryMetric = allMetrics[0]?.[0] ?? "max_height"
  const trendQuery = useTrend(undefined, elementId, primaryMetric, period)

  // Build metric card data from registry + PRs + findings
  const metricCards = allMetrics.map(([name, def]) => {
    const pr = prData?.prs.find(p => p.metric_name === name)
    const finding = elementFindings.find(f => f.metric === name)
    const trendForMetric =
      primaryMetric === name && trendQuery.data ? trendQuery.data.trend : undefined
    const isWarning = finding?.severity === "warning"

    return {
      name,
      label: def.label_ru,
      unit: def.unit,
      direction: def.direction,
      value: pr?.value ?? 0,
      isPr: !!pr,
      isWarning,
      trend: trendForMetric,
    }
  })

  // Visible metric cards (4 by default, all when expanded)
  const visibleCards = showAllMetrics ? metricCards : metricCards.slice(0, 4)

  return (
    <div className="space-y-4">
      {/* Back link */}
      <div>
        <Link
          href="/progress"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-3 w-3" />
          {tp("backToElements")}
        </Link>
      </div>

      {/* Element title */}
      <h1 className="sh-display-md">{elementName}</h1>

      {/* Top 3 diagnostic alerts */}
      {topAlerts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-ink-mute">{tp("alerts")}</p>
          {topAlerts.map(finding => (
            <div
              key={`${finding.metric}-${finding.severity}`}
              className={`rounded-xl border p-3 ${
                finding.severity === "warning"
                  ? "border-yellow-500/20 bg-yellow-500/5"
                  : "border-blue-500/20 bg-blue-500/5"
              }`}
            >
              <p className="text-sm font-medium">{finding.message}</p>
              {finding.detail && <p className="mt-0.5 text-xs text-ink-mute">{finding.detail}</p>}
            </div>
          ))}
        </div>
      )}

      {topAlerts.length === 0 && elementFindings.length === 0 && (
        <p className="text-xs text-ink-mute">{tp("noAlerts")}</p>
      )}

      {/* 2x2 metric cards grid */}
      {visibleCards.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {visibleCards.map(card => (
            <MetricCard
              key={card.name}
              label={card.label}
              value={card.value}
              unit={card.unit}
              direction={card.direction}
              trend={card.trend}
              isPr={card.isPr}
              isWarning={card.isWarning}
              onClick={() => {
                router.push(`/progress?element=${elementId}&metric=${card.name}`)
              }}
            />
          ))}
        </div>
      )}

      {/* Expand all metrics */}
      {allMetrics.length > 4 && (
        <button
          type="button"
          onClick={() => setShowAllMetrics(prev => !prev)}
          className="flex w-full items-center justify-center gap-1 rounded-xl border border-hairline py-2 text-xs font-medium text-ink-mute transition-colors hover:bg-muted/50"
        >
          {tp("allMetrics", { count: allMetrics.length })}
          <ChevronDown
            className={`h-3 w-3 transition-transform ${showAllMetrics ? "rotate-180" : ""}`}
          />
        </button>
      )}

      {/* Primary trend chart */}
      <PeriodSelector value={period} onChange={setPeriod} />

      {trendQuery.data && trendQuery.data.data_points.length > 0 && (
        <TrendChart data={trendQuery.data} />
      )}

      {(!trendQuery.data || trendQuery.data.data_points.length === 0) && !trendQuery.isLoading && (
        <p className="py-10 text-center text-sm text-ink-mute">{tc("noData")}</p>
      )}
    </div>
  )
}
