"use client"

import { Line, LineChart, ReferenceArea, ResponsiveContainer, XAxis, YAxis } from "recharts"
import { useTranslations } from "@/i18n"
import { parseFormatDecimals } from "@/lib/format"
import type { TrendResponse } from "@/types"

// #495: TrendChart now takes an optional `format` prop (the backend
// Python format-spec, e.g. ".0f"). The component uses parseFormatDecimals
// to derive the right decimal count for the PR line below the chart.
// Pre-fix: hardcoded `toFixed(3)` ignored the backend's per-metric
// format-spec — `.0f` metrics like rotation_speed rendered as
// "540.000" instead of "540".
export function TrendChart({ data, format }: { data: TrendResponse; format?: string }) {
  const tc = useTranslations("common")
  const tp = useTranslations("progress")

  if (!data.data_points.length) {
    return <p className="text-center text-muted-foreground py-10">{tc("noData")}</p>
  }

  const refMin = data.reference_range?.min
  const refMax = data.reference_range?.max

  const trendLabel = tp(`trends.${data.trend}`)

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span>{data.metric_name}</span>
        <span
          className={
            data.trend === "improving"
              ? ""
              : data.trend === "declining"
                ? ""
                : "text-muted-foreground"
          }
          style={
            data.trend === "improving"
              ? { color: "oklch(var(--score-good))" }
              : data.trend === "declining"
                ? { color: "oklch(var(--score-bad))" }
                : undefined
          }
        >
          {trendLabel}
        </span>
      </div>
      <div className="h-[200px] sm:h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.data_points} margin={{ top: 10, right: 10, bottom: 0, left: -10 }}>
            {refMin !== undefined && refMax !== undefined && (
              <ReferenceArea
                y1={refMin}
                y2={refMax}
                fill="oklch(0.723 0.219 149)"
                fillOpacity={0.1}
                ifOverflow="extendDomain"
              />
            )}
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="value"
              // #833: project color system is OKLCH, so --primary resolves to
              // `oklch(...)`. `hsl(var(--primary))` wrapped an OKLCH token inside
              // hsl() → `hsl(oklch(...))` is an invalid CSS color and recharts
              // rendered the trend line with no stroke (transparent). Use the
              // raw OKLCH token like frame-metrics-chart.tsx does.
              stroke="oklch(var(--primary))"
              strokeWidth={2}
              dot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {data.current_pr !== null && (
        <p className="text-sm font-medium" style={{ color: "oklch(var(--score-mid))" }}>
          PR: {data.current_pr.toFixed(parseFormatDecimals(format))}
        </p>
      )}
    </div>
  )
}
