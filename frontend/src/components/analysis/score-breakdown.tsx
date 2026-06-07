"use client"

import { useMemo } from "react"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import type { MultiDimensionalScore } from "@/types"
import { useTranslations } from "@/i18n"
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

interface Props {
  score: MultiDimensionalScore
}

function getBarColor(value: number): string {
  if (value >= 7) return "oklch(var(--score-good))"
  if (value >= 5) return "oklch(var(--score-mid))"
  return "oklch(var(--score-bad))"
}

export function ScoreBreakdown({ score }: Props) {
  const t = useTranslations("analysis")

  const data = useMemo(() => {
    return score.subscores.map((s) => ({
      label: s.label_ru,
      value: s.value,
    }))
  }, [score.subscores])

  if (score.subscores.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("overallScore", { score: score.overall.toFixed(1) })}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("noData")}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("overallScore", { score: score.overall.toFixed(1) })}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full rounded-2xl border border-border bg-background p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 24, left: 8 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                angle={-30}
                textAnchor="end"
                interval={0}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 10]}
                width={30}
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "oklch(var(--background))",
                  border: "1px solid oklch(var(--border))",
                  borderRadius: "12px",
                  fontSize: 12,
                }}
                labelStyle={{ color: "oklch(var(--foreground))" }}
                formatter={(value) => [t("scoreLabel", { value: Number(value ?? 0).toFixed(1) }), ""]}
              />
              <ReferenceLine y={5} stroke="oklch(var(--foreground))" strokeDasharray="4 4" />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.value)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
      <CardFooter className="flex justify-between text-xs text-muted-foreground">
        <span>
          {t("dataQuality", {
            quality: t(`quality_${score.data_quality}` as Parameters<typeof t>[0]),
          })}
        </span>
        <span>
          {t("skeletonReliability", {
            reliability: t(`reliability_${score.skeleton_reliability}` as Parameters<typeof t>[0]),
          })}
        </span>
      </CardFooter>
    </Card>
  )
}
