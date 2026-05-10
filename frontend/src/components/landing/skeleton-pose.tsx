"use client"

import { useState } from "react"
import { useMountEffect } from "@/lib/useMountEffect"

export interface SkeletonPoseProps {
  role?: string
  "aria-label"?: string
}

const BASE_POINTS = [
  { x: 0.5, y: 0.15 },
  { x: 0.5, y: 0.3 },
  { x: 0.38, y: 0.32 },
  { x: 0.3, y: 0.48 },
  { x: 0.22, y: 0.62 },
  { x: 0.62, y: 0.32 },
  { x: 0.7, y: 0.48 },
  { x: 0.78, y: 0.62 },
  { x: 0.5, y: 0.52 },
  { x: 0.42, y: 0.68 },
  { x: 0.36, y: 0.85 },
  { x: 0.32, y: 0.98 },
  { x: 0.58, y: 0.68 },
  { x: 0.64, y: 0.85 },
  { x: 0.68, y: 0.98 },
]

const LINES: readonly [number, number][] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [1, 5],
  [5, 6],
  [6, 7],
  [1, 8],
  [8, 9],
  [9, 10],
  [10, 11],
  [8, 12],
  [12, 13],
  [13, 14],
] as const

export function SkeletonPose({ role, "aria-label": ariaLabel }: SkeletonPoseProps) {
  const [frame, setFrame] = useState(0)

  useMountEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % 60), 50)
    return () => clearInterval(id)
  })

  const points = BASE_POINTS.map((p, i) => {
    const offset = Math.sin((frame + i * 10) * 0.1) * 0.015
    return { x: p.x + offset, y: p.y + offset * 0.5 }
  })

  return (
    <svg
      viewBox="0 0 1 1"
      className="absolute inset-0 h-full w-full"
      {...(role ? { role, "aria-label": ariaLabel } : { "aria-hidden": "true" as const })}
    >
      <title>{ariaLabel ?? "Skeleton pose animation"}</title>
      {LINES.map(([a, b]) => (
        <line
          key={`${a}-${b}`}
          x1={points[a].x}
          y1={points[a].y}
          x2={points[b].x}
          y2={points[b].y}
          stroke="rgba(255,255,255,0.9)"
          strokeWidth="0.008"
          strokeLinecap="round"
        />
      ))}
      {points.map((p, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: skeleton joints are positionally ordered, index IS the identity
        <circle key={`joint-${i}`} cx={p.x} cy={p.y} r="0.012" fill="rgba(255,255,255,0.95)" />
      ))}
    </svg>
  )
}
