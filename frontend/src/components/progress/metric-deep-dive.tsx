"use client"

import Link from "next/link"
import { useState } from "react"
import { ArrowLeft, Trophy } from "lucide-react"
import { useTranslations } from "@/i18n"
import { parseFormatDecimals } from "@/lib/format"
import { useMetricRegistry, useTrend, useDiagnostics, usePRs } from "@/lib/api/metrics"
import { TrendChart } from "@/components/progress/trend-chart"
import { PeriodSelector } from "@/components/progress/period-selector"
import { ReferenceRangeBar } from "@/components/progress/reference-range-bar"
import type { TrendResponse } from "@/types"

interface MetricDeepDiveProps {
  elementId: string
  metricName: string
}

export function MetricDeepDive({ elementId, metricName }: MetricDeepDiveProps) {
  const tp = useTranslations("progress")
  const tc = useTranslations("common")
  const [period, setPeriod] = useState("30d")

  const { data: registry } = useMetricRegistry()
  const trendQuery = useTrend(undefined, elementId, metricName, period)
  const { data: diagnostics } = useDiagnostics()
  const { data: prData } = usePRs(undefined, elementId)

  const metricDef = registry?.[metricName]
  const label = metricDef?.label_ru ?? metricName
  const unit = metricDef?.unit ?? ""
  const direction = metricDef?.direction ?? "higher"

  // Filter findings for this element + metric
  const finding = diagnostics?.findings?.find(
    f => f.element === elementId && f.metric === metricName,
  )

  // PR for this specific metric
  const pr = prData?.prs.find(p => p.metric_name === metricName)

  // Ideal range from metric definition (tuple [low, high])
  const idealLow = metricDef?.ideal_range?.[0] ?? 0
  const idealHigh = metricDef?.ideal_range?.[1] ?? 100

  // Current (latest) value from trend data
  const latestValue =
    trendQuery.data && trendQuery.data.data_points.length > 0
      ? trendQuery.data.data_points[trendQuery.data.data_points.length - 1].value
      : 0

  return (
    <div className="mx-auto max-w-2xl space-y-4 sm:max-w-3xl">
      {/* Back link */}
      <div>
        <Link
          href={`/progress?element=${elementId}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-3 w-3" />
          {tp("backToMetrics")}
        </Link>
      </div>

      {/* Header: metric name + value + unit */}
      <div>
        <h2 className="text-lg font-semibold">{label}</h2>
        {trendQuery.data && trendQuery.data.data_points.length > 0 && (
          <p className="text-2xl font-bold tabular-nums">
            {latestValue.toFixed(parseFormatDecimals(metricDef?.format))}
            {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
          </p>
        )}
      </div>

      {/* Period selector */}
      <PeriodSelector value={period} onChange={setPeriod} />

      {/* Trend chart */}
      {trendQuery.data && trendQuery.data.data_points.length > 0 && (
        <TrendChart data={trendQuery.data as TrendResponse} format={metricDef?.format} />
      )}

      {/* PR section */}
      {pr && (
        <div className="flex items-center gap-2 rounded-2xl border border-hairline p-4">
          <Trophy className="h-4 w-4 text-yellow-500" />
          <div>
            <p className="text-xs text-muted-foreground">{tp("personalRecord")}</p>
            <p className="text-sm font-semibold tabular-nums">
              {pr.value.toFixed(parseFormatDecimals(metricDef?.format))}
              {unit && (
                <span className="ml-0.5 text-xs font-normal text-muted-foreground">{unit}</span>
              )}
            </p>
          </div>
        </div>
      )}

      {/* Reference range bar */}
      {metricDef && (
        <div className="space-y-2 rounded-2xl border border-hairline p-4">
          <p className="text-xs text-muted-foreground">{tp("referenceRange")}</p>
          <ReferenceRangeBar
            value={latestValue}
            min={idealLow * 0.5}
            max={idealHigh * 1.5}
            idealLow={idealLow}
            idealHigh={idealHigh}
            direction={direction}
          />
          <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums">
            <span>{(idealLow * 0.5).toFixed(1)}</span>
            <span className="text-green-600 dark:text-green-400">
              {idealLow.toFixed(1)} — {idealHigh.toFixed(1)}
            </span>
            <span>{(idealHigh * 1.5).toFixed(1)}</span>
          </div>
        </div>
      )}

      {/* Diagnostic finding */}
      {finding && (
        <div
          className={`rounded-2xl border p-4 ${
            finding.severity === "warning"
              ? "border-yellow-500/20 bg-yellow-500/5"
              : "border-blue-500/20 bg-blue-500/5"
          }`}
        >
          <p className="text-sm font-medium">{finding.message}</p>
          {finding.detail && <p className="mt-1 text-xs text-muted-foreground">{finding.detail}</p>}
        </div>
      )}

      {/* No data state */}
      {(!trendQuery.data || trendQuery.data.data_points.length === 0) && !trendQuery.isLoading && (
        <p className="py-10 text-center text-muted-foreground">{tc("noData")}</p>
      )}
    </div>
  )
}
