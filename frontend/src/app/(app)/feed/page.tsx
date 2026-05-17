"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { SessionCard } from "@/components/session/session-card"
import { SkeletonCard } from "@/components/skeleton-card"
import { ErrorState } from "@/components/error-state"
import { DemoBadge } from "@/components/demo/demo-badge"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { useTranslations } from "@/i18n"
import { useSessions, useBulkDeleteSessions } from "@/lib/api/sessions"
import { ELEMENT_TYPE_KEYS } from "@/lib/constants"
import { Upload } from "lucide-react"
import { EmptyState, FirstAnalysisCelebration } from "@/components/onboarding"
import { NoVideoGuide } from "./no-video-guide"

export default function FeedPage() {
  const query = useSessions()
  const { isFirstLoad, isError } = usePageStatus([query])
  const tf = useTranslations("feed")
  const tc = useTranslations("common")
  const te = useTranslations("elements")
  const tEmpty = useTranslations("emptyStates")
  const td = useTranslations("demo")

  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const bulkDelete = useBulkDeleteSessions()

  const [elementFilter, setElementFilter] = useState("")
  const [dateFilter, setDateFilter] = useState("all")
  const [showGuide, setShowGuide] = useState(false)

  const totalSessions = query.data?.sessions.length ?? 0

  const filteredSessions = useMemo(() => {
    if (!query.data?.sessions) return []
    let sessions = [...query.data.sessions]
    if (elementFilter) {
      sessions = sessions.filter(s => s.element_type === elementFilter)
    }
    if (dateFilter !== "all") {
      const days = { "7d": 7, "30d": 30, "90d": 90 }[dateFilter]
      if (days) {
        const cutoff = Date.now() - days * 86400000
        sessions = sessions.filter(s => new Date(s.created_at).getTime() >= cutoff)
      }
    }
    return sessions
  }, [query.data, elementFilter, dateFilter])

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleBulkDelete = () => {
    if (!window.confirm(tf("bulkDeleteConfirm"))) return
    bulkDelete.mutate(Array.from(selectedIds), {
      onSuccess: () => {
        setSelectedIds(new Set())
        setSelectionMode(false)
      },
    })
  }

  if (isFirstLoad) {
    return (
      <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (isError) return <ErrorState onRetry={() => query.refetch()} />

  const showDemoTile = totalSessions < 3

  if (!totalSessions) {
    return (
      <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
        <Link
          href="/sessions/demo-axel"
          className="block rounded-2xl border border-primary/20 bg-primary/5 p-3 sm:p-4 transition-colors hover:bg-primary/10"
        >
          <div className="flex items-center gap-2">
            <span className="font-medium">{te("axel")}</span>
            <DemoBadge />
          </div>
          <p className="mt-1 text-sm text-ink-mute">{td("demoSessionLabel")}</p>
        </Link>
        <EmptyState
          icon={<Upload className="h-7 w-7 text-primary" />}
          title={tEmpty("feedTitle")}
          description={tEmpty("feedDesc")}
          primaryAction={{ label: tEmpty("feedAction"), href: "/upload" }}
          secondaryAction={{
            label: tf("noVideo"),
            href: "#",
            onClick: (e: React.MouseEvent) => {
              e.preventDefault()
              setShowGuide(!showGuide)
            },
          }}
        />
        {showGuide && <NoVideoGuide />}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
      <FirstAnalysisCelebration hasSessions={totalSessions > 0} />
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => {
            setSelectionMode(!selectionMode)
            setSelectedIds(new Set())
          }}
          className="text-sm text-ink-mute hover:text-foreground"
        >
          {selectionMode ? tc("cancel") : tf("select")}
        </button>
        {selectionMode && selectedIds.size > 0 && (
          <button
            type="button"
            onClick={handleBulkDelete}
            disabled={bulkDelete.isPending}
            className="text-sm text-destructive hover:text-destructive/80"
          >
            {bulkDelete.isPending
              ? tc("saving")
              : tf("deleteSelected", { count: selectedIds.size })}
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={elementFilter}
          onChange={e => setElementFilter(e.target.value)}
          className="rounded-lg border border-hairline bg-transparent px-2 py-1 text-sm"
        >
          <option value="">{tf("allElements")}</option>
          {ELEMENT_TYPE_KEYS.map(key => (
            <option key={key} value={key}>
              {te(key)}
            </option>
          ))}
        </select>
        <div className="flex gap-1">
          {(["7d", "30d", "90d", "all"] as const).map(d => (
            <button
              key={d}
              type="button"
              onClick={() => setDateFilter(d)}
              className={`rounded-lg px-2 py-1 text-xs ${dateFilter === d ? "bg-primary text-primary-foreground" : "border border-hairline hover:bg-muted"}`}
            >
              {tf(`period${d}`)}
            </button>
          ))}
        </div>
        <Link
          href="/upload"
          className="ml-auto flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <Upload className="h-4 w-4" />
          {tEmpty("feedAction")}
        </Link>
      </div>

      {filteredSessions.length === 0 && !showDemoTile ? (
        <p className="py-10 text-center text-ink-mute">{tf("noSessions")}</p>
      ) : (
        <>
          {showDemoTile && (
            <Link
              href="/sessions/demo-axel"
              className="block rounded-2xl border border-primary/20 bg-primary/5 p-3 sm:p-4 transition-colors hover:bg-primary/10"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">{te("axel")}</span>
                <DemoBadge />
              </div>
              <p className="mt-1 text-sm text-ink-mute">{td("demoSessionLabel")}</p>
            </Link>
          )}
          {filteredSessions.map(session => (
            <SessionCard
              key={session.id}
              session={session}
              selectable={selectionMode}
              selected={selectedIds.has(session.id)}
              onSelect={toggleSelect}
            />
          ))}
        </>
      )}
    </div>
  )
}
