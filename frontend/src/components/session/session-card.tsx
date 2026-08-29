"use client"

import { Award, Clock, Loader2 } from "lucide-react"
import Link from "next/link"
import type React from "react"
import { useTranslations } from "@/i18n"
import type { Session } from "@/types"
import { useElementLabel, useMetricRegistry } from "@/hooks/use-metric-registry"

/** Decimal count from a backend format spec like ".3f" / ".0f" / ".1f".
 * Mirrors personal-records.tsx:47 (#446) and metric-row.tsx (#510). Defaults
 * to 2 when the spec is absent/unparseable. */
function decimalsFromFormat(format: string | null | undefined): number {
  return Number(format?.match(/\d+(?=f)/)?.[0] ?? 2)
}

function relativeTime(
  dateStr: string,
  t: (key: string, params?: Record<string, number>) => string,
): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t("justNow")
  if (mins < 60) return t("minsAgo", { n: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t("hoursAgo", { n: hours })
  const days = Math.floor(hours / 24)
  return t("daysAgo", { n: days })
}

function scoreStyle(score: number | null): React.CSSProperties {
  if (score === null) return { color: "oklch(var(--muted-foreground))" }
  if (score >= 0.8) return { color: "oklch(var(--score-good))" }
  if (score >= 0.5) return { color: "oklch(var(--score-mid))" }
  return { color: "oklch(var(--score-bad))" }
}

interface SessionCardProps {
  session: Session
  selectable?: boolean
  selected?: boolean
  onSelect?: (id: string) => void
}

export function SessionCard({ session, selectable, selected, onSelect }: SessionCardProps) {
  const hasPR = session.metrics.some(m => m.is_pr)
  const elementLabel = useElementLabel()
  const { data: registry } = useMetricRegistry()
  const ts = useTranslations("session")

  return (
    <Link href={`/sessions/${session.id}`} className="block">
      <div className="rounded-2xl border border-border p-3 sm:p-4 hover:bg-accent/30 transition-colors">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center min-w-0">
            {selectable && (
              <input
                type="checkbox"
                checked={selected}
                onChange={() => onSelect?.(session.id)}
                className="mr-2 h-4 w-4 shrink-0"
                onClick={e => e.stopPropagation()}
              />
            )}
            <div className="min-w-0">
              <p className="font-medium truncate">
                {elementLabel(session.element_type ?? "unknown")}
              </p>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3 shrink-0" />
                {relativeTime(session.created_at, ts)}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {hasPR && <Award className="h-4 w-4" style={{ color: "oklch(var(--accent-gold))" }} />}
            {session.overall_score !== null && (
              <span className="text-sm font-medium" style={scoreStyle(session.overall_score)}>
                {Math.round(session.overall_score * 100)}%
              </span>
            )}
          </div>
        </div>

        {session.status !== "completed" ? (
          <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            {session.status === "running" || session.status === "processing"
              ? ts("analyzing")
              : ts("waiting")}
          </div>
        ) : (
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            {session.metrics.slice(0, 3).map(m => (
              <span key={m.metric_name}>
                {m.metric_name}:{" "}
                {m.metric_value.toFixed(decimalsFromFormat(registry?.[m.metric_name]?.format))}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  )
}
