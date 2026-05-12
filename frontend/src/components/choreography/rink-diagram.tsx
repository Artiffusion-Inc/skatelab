"use client"

import { useCallback, useMemo, useRef } from "react"
import { useTranslations } from "@/i18n"
import type { LayoutElement, TrackType } from "@/types/choreography"
import { TRACK_CONFIG } from "@/types/choreography"
import { useChoreographyEditor } from "./editor/store"
import { JumpTrace, SequenceTrace, SpinMarker } from "./rink-figures"
import { FlowPaths } from "./rink-flow"

const VW = 30
const VH = 61
const PAD = 0.5

interface RinkElement {
  id: string
  code: string
  x: number
  y: number
  trackType: TrackType
  timestamp: number
}

function trackColor(trackType: TrackType): string {
  return TRACK_CONFIG[trackType].hex
}

function trackLabel(trackType: TrackType, t: (key: string) => string): string {
  return trackType === "jumps"
    ? t("rink.jump")
    : trackType === "spins"
      ? t("rink.spin")
      : t("rink.sequence")
}

function autoLayout(
  elements: { id: string; code: string; trackType: TrackType; timestamp: number }[],
  _duration: number,
): RinkElement[] {
  if (elements.length === 0) return []

  const sorted = [...elements].sort((a, b) => a.timestamp - b.timestamp)
  const usableW = VW - PAD * 2
  const usableH = VH - PAD * 2

  return sorted.map((el, i) => {
    const col = Math.floor(i / 5)
    const row = i % 5
    const colDir = col % 2 === 0 ? 1 : -1
    const rowNorm = colDir === 1 ? row / 4 : 1 - row / 4
    const colNorm = col / Math.max(1, Math.ceil(sorted.length / 5) - 1)
    return {
      ...el,
      x: PAD + rowNorm * usableW,
      y: PAD + colNorm * usableH,
    }
  })
}

export function RinkDiagram({
  className,
  elements: propElements,
}: {
  className?: string
  elements?: LayoutElement[]
}) {
  const t = useTranslations("choreography")
  const storeElements = useChoreographyEditor(s => s.elements)
  const selectedId = useChoreographyEditor(s => s.selectedElementId)
  const select = useChoreographyEditor(s => s.setSelectedElement)
  const updatePos = useChoreographyEditor(s => s.updateElementPosition)
  const musicDuration = useChoreographyEditor(s => s.musicDuration)

  const isReadonly = !!propElements
  const _elements = propElements ?? storeElements
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{ id: string; sx: number; sy: number; ox: number; oy: number } | null>(
    null,
  )

  const rinkElements = useMemo((): RinkElement[] => {
    if (isReadonly) {
      return (propElements ?? []).map((el, i) => {
        const tt: TrackType = el.code.includes("Sp")
          ? "spins"
          : el.code.startsWith("StSq") || el.code.startsWith("ChSq")
            ? "sequences"
            : "jumps"
        return {
          id: `ro-${i}`,
          code: el.code,
          trackType: tt,
          timestamp: el.timestamp,
          x: el.position?.x ?? 0,
          y: el.position?.y ?? 0,
        }
      })
    }

    const withPos: RinkElement[] = storeElements
      .filter(
        (el): el is typeof el & { position: NonNullable<typeof el.position> } => !!el.position,
      )
      .map(el => ({
        id: el.id,
        code: el.code,
        trackType: el.trackType,
        timestamp: el.timestamp,
        x: el.position.x,
        y: el.position.y,
      }))

    const withoutPos = storeElements.filter(el => !el.position)
    const auto = autoLayout(withoutPos, musicDuration)

    return [...withPos, ...auto].sort((a, b) => a.timestamp - b.timestamp)
  }, [isReadonly, propElements, storeElements, musicDuration])

  const toSvg = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    return {
      x: ((clientX - rect.left) / rect.width) * VW,
      y: ((clientY - rect.top) / rect.height) * VH,
    }
  }, [])

  const onPointerDown = useCallback(
    (e: React.PointerEvent, el: RinkElement) => {
      e.preventDefault()
      e.stopPropagation()
      select(el.id)
      const pt = toSvg(e.clientX, e.clientY)
      dragRef.current = {
        id: el.id,
        sx: e.clientX,
        sy: e.clientY,
        ox: pt.x - el.x,
        oy: pt.y - el.y,
      }
      ;(e.target as Element).setPointerCapture(e.pointerId)
    },
    [select, toSvg],
  )

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragRef.current) return
      const pt = toSvg(e.clientX, e.clientY)
      const nx = Math.max(PAD, Math.min(VW - PAD, pt.x - dragRef.current.ox))
      const ny = Math.max(PAD, Math.min(VH - PAD, pt.y - dragRef.current.oy))
      updatePos(dragRef.current.id, nx, ny)
    },
    [toSvg, updatePos],
  )

  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])

  const onRinkClick = useCallback(
    (e: React.MouseEvent) => {
      if ((e.target as Element).closest("[data-el-marker]")) return
      select(null)
    },
    [select],
  )

  return (
    <div className={`w-full ${className ?? ""}`}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: interactive SVG canvas with pointer events */}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        className="w-full select-none"
        style={{ borderRadius: "var(--radius-sm)", overflow: "hidden" }}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={onRinkClick}
      >
        <title>{t("rink.title")}</title>

        {/* Ice surface */}
        <rect x="0" y="0" width={VW} height={VH} fill="oklch(0.97 0.01 240)" />

        {/* Boundary */}
        <rect
          x="0"
          y="0"
          width={VW}
          height={VH}
          rx={7.5}
          fill="none"
          stroke="#dc2626"
          strokeWidth={0.15}
        />

        {/* Centre line */}
        <line
          x1="0"
          y1={VH / 2}
          x2={VW}
          y2={VH / 2}
          stroke="#dc2626"
          strokeWidth={0.12}
        />

        {/* Blue lines */}
        <line x1="0" y1={8.5} x2={VW} y2={8.5} stroke="#2563eb" strokeWidth={0.1} />
        <line x1="0" y1={52.5} x2={VW} y2={52.5} stroke="#2563eb" strokeWidth={0.1} />

        {/* End lines */}
        <line x1="0" y1={4} x2={VW} y2={4} stroke="#dc2626" strokeWidth={0.1} />
        <line x1="0" y1={57} x2={VW} y2={57} stroke="#dc2626" strokeWidth={0.1} />

        {/* Centre circle */}
        <circle
          cx={VW / 2}
          cy={VH / 2}
          r={1.5}
          fill="none"
          stroke="#dc2626"
          strokeWidth={0.1}
        />
        <circle cx={VW / 2} cy={VH / 2} r={0.12} fill="#dc2626" />

        {/* Face-off circles (4) */}
        {[
          [VW / 2 - 6, VH / 2 - 11],
          [VW / 2 + 6, VH / 2 - 11],
          [VW / 2 - 6, VH / 2 + 11],
          [VW / 2 + 6, VH / 2 + 11],
        ].map(([cx, cy]) => (
          <circle
            key={`face-${cx}-${cy}`}
            cx={cx}
            cy={cy}
            r={3}
            fill="none"
            stroke="#dc2626"
            strokeWidth={0.08}
          />
        ))}

        {/* Face-off dots (5) */}
        {[
          [VW / 2, VH / 2],
          [VW / 2 - 6, VH / 2 - 11],
          [VW / 2 + 6, VH / 2 - 11],
          [VW / 2 - 6, VH / 2 + 11],
          [VW / 2 + 6, VH / 2 + 11],
        ].map(([cx, cy]) => (
          <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={0.15} fill="#dc2626" />
        ))}

        {/* Corner creases (4) — 180° arcs */}
        {[
          { x: 0, y: 0, start: 0, end: 90 },
          { x: VW, y: 0, start: 90, end: 180 },
          { x: 0, y: VH, start: 270, end: 360 },
          { x: VW, y: VH, start: 180, end: 270 },
        ].map((c, i) => {
          const r = 1.8
          const largeArcFlag = 0
          const sweepFlag = 1
          const x1 = c.x === 0 ? r : c.x - r
          const y1 = c.y === 0 ? 0 : c.y
          const x2 = c.x === 0 ? 0 : c.x
          const y2 = c.y === 0 ? r : c.y - r
          return (
            <path
              key={`crease-${i}`}
              d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArcFlag} ${sweepFlag} ${x2} ${y2}`}
              fill="none"
              stroke="#dc2626"
              strokeWidth={0.08}
            />
          )
        })}

        {/* Flow paths between sequential elements */}
        <FlowPaths elements={rinkElements} />

        {/* Elements */}
        {rinkElements.map((el, i) => {
          const color = trackColor(el.trackType)
          const selected = el.id === selectedId
          const num = i + 1
          return (
            <g
              key={el.id}
              data-el-marker
              data-el-id={el.id}
              onPointerDown={isReadonly ? undefined : e => onPointerDown(e, el)}
              style={{ cursor: isReadonly ? "default" : "grab" }}
            >
              {/* Selection ring */}
              {selected && (
                <circle
                  cx={el.x}
                  cy={el.y}
                  r={2}
                  fill="none"
                  stroke={color}
                  strokeWidth={0.2}
                  opacity={0.6}
                />
              )}

              {/* Trace figure by type */}
              {el.trackType === "jumps" && (
                <JumpTrace x={el.x} y={el.y} code={el.code} color={color} elementId={el.id} />
              )}
              {el.trackType === "spins" && <SpinMarker x={el.x} y={el.y} color={color} />}
              {el.trackType === "sequences" && (
                <SequenceTrace x={el.x} y={el.y} code={el.code} color={color} elementId={el.id} />
              )}

              {/* Number badge */}
              <circle
                cx={el.x + 1.2}
                cy={el.y - 1.0}
                r={0.7}
                fill="oklch(var(--background))"
                stroke={color}
                strokeWidth={0.12}
              />
              <text
                x={el.x + 1.2}
                y={el.y - 0.65}
                textAnchor="middle"
                fontSize={0.85}
                fill={color}
                fontWeight="bold"
              >
                {num}
              </text>

              {/* Code label */}
              <text
                x={el.x}
                y={el.y + 2.2}
                textAnchor="middle"
                fontSize={0.9}
                fill="oklch(var(--foreground))"
                fontWeight="600"
              >
                {el.code}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="mt-2 flex flex-wrap gap-3 px-1 text-[10px] text-muted-foreground">
        {(["jumps", "spins", "sequences"] as TrackType[]).map(tt => (
          <div key={tt} className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: trackColor(tt) }} />
            {trackLabel(tt, t)}
          </div>
        ))}
      </div>
    </div>
  )
}
