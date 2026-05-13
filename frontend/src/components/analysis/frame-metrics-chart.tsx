"use client"

import { useMemo } from "react"
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts"
import { useAnalysisStore } from "@/stores/analysis"
import type { FrameMetrics, PhasesData, PoseData } from "@/types"
import { useTranslations } from "@/i18n"

interface Props {
  poseData: PoseData
  frameMetrics: FrameMetrics
  phases?: PhasesData | null
  totalFrames: number
}

const METRIC_COLORS: Record<string, string> = {
  knee_angles_r: "#ef4444",
  knee_angles_l: "#f97316",
  hip_angles_r: "#22c55e",
  hip_angles_l: "#14b8a6",
  trunk_lean: "#eab308",
  com_height: "#3b82f6",
}

export function FrameMetricsChart({ poseData, frameMetrics, phases, totalFrames }: Props) {
  const t = useTranslations("analysis")
  const { currentFrame, setCurrentFrame } = useAnalysisStore()

  const data = useMemo(() => {
    return poseData.frames.map((frame, i) => ({
      frame,
      knee_angles_r: frameMetrics.knee_angles_r[i] ?? null,
      knee_angles_l: frameMetrics.knee_angles_l[i] ?? null,
      hip_angles_r: frameMetrics.hip_angles_r[i] ?? null,
      hip_angles_l: frameMetrics.hip_angles_l[i] ?? null,
      trunk_lean: frameMetrics.trunk_lean[i] ?? null,
      com_height: frameMetrics.com_height[i] ?? null,
    }))
  }, [poseData.frames, frameMetrics])

  const handleClick = (state: unknown) => {
    const s = state as { activePayload?: Array<{ payload: { frame: number } }> }
    if (s.activePayload?.[0]?.payload?.frame !== undefined) {
      setCurrentFrame(s.activePayload[0].payload.frame)
    }
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{t("frameMetrics")}</h3>
      <div className="h-48 w-full rounded-2xl border border-border bg-background p-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            onClick={handleClick}
            margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
          >
            <XAxis
              dataKey="frame"
              type="number"
              domain={[0, totalFrames]}
              tick={false}
              axisLine={false}
            />
            <YAxis width={30} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: "oklch(var(--background))",
                border: "1px solid oklch(var(--border))",
                borderRadius: "12px",
                fontSize: 12,
              }}
              labelStyle={{ color: "oklch(var(--foreground))" }}
              itemStyle={{ fontSize: 11 }}
            />
            {phases?.takeoff && (
              <ReferenceLine
                x={phases.takeoff.frame}
                stroke="oklch(var(--score-good))"
                strokeDasharray="3 3"
              />
            )}
            {phases?.peak && (
              <ReferenceLine
                x={phases.peak.frame}
                stroke="oklch(var(--score-mid))"
                strokeDasharray="3 3"
              />
            )}
            {phases?.landing && (
              <ReferenceLine
                x={phases.landing.frame}
                stroke="oklch(var(--score-bad))"
                strokeDasharray="3 3"
              />
            )}
            <ReferenceLine x={currentFrame} stroke="oklch(var(--primary))" strokeWidth={2} />
            <Area
              type="monotone"
              dataKey="com_height"
              stroke={METRIC_COLORS.com_height}
              fill={METRIC_COLORS.com_height}
              fillOpacity={0.1}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="knee_angles_r"
              stroke={METRIC_COLORS.knee_angles_r}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="knee_angles_l"
              stroke={METRIC_COLORS.knee_angles_l}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="hip_angles_r"
              stroke={METRIC_COLORS.hip_angles_r}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="hip_angles_l"
              stroke={METRIC_COLORS.hip_angles_l}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="trunk_lean"
              stroke={METRIC_COLORS.trunk_lean}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        {Object.entries(METRIC_COLORS).map(([key, color]) => (
          <div key={key} className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-muted-foreground">{t(key)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
