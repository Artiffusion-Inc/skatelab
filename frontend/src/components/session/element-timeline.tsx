"use client"

import { useMemo } from "react"

interface ElementSegment {
  id: string
  element_type: string
  element_name: string | null
  start_frame: number
  end_frame: number
  confidence: number
  phases_json?: {
    takeoff: { frame: number }
    peak: { frame: number }
    landing: { frame: number }
  } | null
}

interface TimelineData {
  segments: ElementSegment[]
  segmentation_confidence: number | null
  segmentation_status: string
}

interface ElementTimelineProps {
  timeline: TimelineData | null | undefined
  totalFrames: number
  fps?: number
  currentFrame?: number
  onSegmentClick?: (segment: ElementSegment) => void
}

const COARSE_COLORS: Record<string, string> = {
  Jump: "bg-blue-500",
  Spin: "bg-purple-500",
  Step: "bg-green-500",
  None: "bg-gray-300",
}

export function ElementTimeline({
  timeline,
  totalFrames,
  fps = 30,
  currentFrame,
  onSegmentClick,
}: ElementTimelineProps) {
  const segments = timeline?.segments ?? []

  const segmentsByType = useMemo(() => {
    const groups: Record<string, ElementSegment[]> = {}
    for (const seg of segments) {
      const type = seg.element_type
      if (!groups[type]) groups[type] = []
      groups[type].push(seg)
    }
    return groups
  }, [segments])

  if (!timeline || timeline.segmentation_status === "pending") {
    return (
      <div className="text-sm text-muted-foreground py-2">
        Segmentation pending...
      </div>
    )
  }

  if (timeline.segmentation_status === "failed") {
    return (
      <div className="text-sm text-destructive py-2">
        Segmentation failed
      </div>
    )
  }

  if (segments.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-2">
        No elements detected
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Elements ({segments.length})</span>
        {timeline.segmentation_confidence != null && (
          <span>Confidence: {(timeline.segmentation_confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      <div className="relative h-8 bg-muted rounded overflow-hidden">
        {segments.map((seg) => {
          const left = (seg.start_frame / totalFrames) * 100
          const width = ((seg.end_frame - seg.start_frame) / totalFrames) * 100
          const colorClass = COARSE_COLORS[seg.element_type] ?? "bg-gray-400"
          const opacity = Math.max(0.3, seg.confidence)
          const isCurrent = currentFrame != null && currentFrame >= seg.start_frame && currentFrame <= seg.end_frame

          return (
            <button
              key={seg.id}
              className={`absolute top-0 bottom-0 ${colorClass} hover:brightness-110 transition-all border border-white/20 ${isCurrent ? "ring-2 ring-white" : ""}`}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                opacity,
              }}
              onClick={() => onSegmentClick?.(seg)}
              title={`${seg.element_name ?? seg.element_type} (${(seg.confidence * 100).toFixed(0)}%)`}
            />
          )
        })}
      </div>
      <div className="flex gap-3 text-xs">
        {Object.entries(COARSE_COLORS)
          .filter(([type]) => type !== "None" && segmentsByType[type])
          .map(([type, colorClass]) => (
            <span key={type} className="flex items-center gap-1">
              <span className={`inline-block w-3 h-3 rounded ${colorClass}`} />
              {type} ({segmentsByType[type].length})
            </span>
          ))}
      </div>
    </div>
  )
}