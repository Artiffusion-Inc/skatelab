"use client"

import { useMemo } from "react"
import { useTranslations } from "@/i18n"
import { useElementsRegistry } from "@/lib/api/choreography"
import type { Layout } from "@/types/choreography"

interface ScoreBarProps {
  layout: Layout | null
  discipline: "mens_singles" | "womens_singles"
  segment: "short_program" | "free_skate"
}

export function ScoreBar({ layout, discipline, segment }: ScoreBarProps) {
  const t = useTranslations("choreography")
  const { data: registry } = useElementsRegistry()

  const stats = useMemo(() => {
    const elements = layout?.elements ?? []
    const bvMap = new Map(registry?.elements.map(e => [e.code, e.base_value]) ?? [])
    const typeMap = new Map(registry?.elements.map(e => [e.code, e.type]) ?? [])

    const jumpCount = elements.filter(e => typeMap.get(e.code) === "jump").length
    const spinCount = elements.filter(e => typeMap.get(e.code) === "spin").length
    const hasStSq = elements.some(e => e.code.startsWith("StSq"))
    const hasChSq = elements.some(e => e.code.startsWith("ChSq"))

    const tes = elements.reduce((sum, el) => {
      const bv = bvMap.get(el.code) ?? 0
      return sum + bv
    }, 0)

    return { jumpCount, spinCount, hasStSq, hasChSq, tes }
  }, [layout, registry])

  const maxJumps = segment === "short_program" ? 3 : 7
  const maxSpins = 3

  const duration = segment === "short_program" ? "2:40" : "4:10"

  return (
    <div className="flex items-center gap-4 overflow-x-auto text-sm sm:gap-6">
      <Stat label={t("score.tes")} value={stats.tes.toFixed(2)} highlight />
      <Stat label={t("score.total")} value={stats.tes > 0 ? (stats.tes * 1.4).toFixed(2) : "0.00"} highlight />
      <div className="h-4 w-px shrink-0 bg-border" />
      <Stat label={t("score.duration")} value={duration} />
      <Stat
        label={t("score.jumps")}
        value={`${stats.jumpCount}/${maxJumps}`}
        warn={stats.jumpCount > maxJumps}
      />
      <Stat
        label={t("score.spins")}
        value={`${stats.spinCount}/${maxSpins}`}
        warn={stats.spinCount > maxSpins}
      />
      <Stat
        label={t("score.steps")}
        value={`${stats.hasStSq ? 1 : 0}/1`}
        warn={!stats.hasStSq}
      />
      <Stat
        label={t("score.choreo")}
        value={`${stats.hasChSq ? 1 : 0}/1`}
        warn={!stats.hasChSq}
      />
    </div>
  )
}

function Stat({
  label,
  value,
  highlight,
  warn,
}: {
  label: string
  value: string
  highlight?: boolean
  warn?: boolean
}) {
  return (
    <div className="shrink-0">
      <p className="text-[10px] leading-tight text-muted-foreground">{label}</p>
      <p
        className={`text-sm font-medium leading-tight ${
          highlight ? "text-primary" : warn ? "text-[oklch(var(--score-bad))]" : ""
        }`}
      >
        {value}
      </p>
    </div>
  )
}
