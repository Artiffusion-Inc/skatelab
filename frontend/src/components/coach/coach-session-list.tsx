"use client"

import { Clock, Loader2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { useLocale, useTranslations } from "@/i18n"
import { EmptyState } from "@/components/onboarding"
import { SESSION_POLLING_STATUSES } from "@/lib/api/sessions"
import type { Session } from "@/types"

type SessionViewStatus = "processing" | "completed" | "failed" | "unavailable"
type SessionFilter = "all" | SessionViewStatus

function viewStatus(session: Session): SessionViewStatus {
  if (session.status === "failed" || session.error_message) return "failed"
  if (session.status === "completed" || session.status === "done") {
    if (session.overall_score === null && session.metrics.length === 0 && !session.pose_data) {
      return "unavailable"
    }
    return "completed"
  }
  return "processing"
}

export function CoachSessionList({
  sessions,
  hasNextPage = false,
  isFetchingNextPage = false,
  onLoadMore,
}: {
  sessions: Session[]
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onLoadMore?: () => void
}) {
  const ts = useTranslations("students")
  const locale = useLocale()
  const [filter, setFilter] = useState<SessionFilter>("all")
  const visibleSessions = sessions.filter(
    session => filter === "all" || viewStatus(session) === filter,
  )

  if (sessions.length === 0) {
    return <EmptyState title={ts("noSessions")} description={ts("noSessionsHint")} />
  }

  return (
    <section aria-label={ts("sessions")} className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{ts("sessions")}</h2>
        <label className="flex items-center gap-2 text-sm text-ink-mute">
          <span className="sr-only">{ts("filterStatus")}</span>
          <select
            aria-label={ts("filterStatus")}
            value={filter}
            onChange={event => setFilter(event.target.value as SessionFilter)}
            className="rounded-lg border border-hairline bg-background px-2 py-1.5 text-sm"
          >
            <option value="all">{ts("allSessions")}</option>
            <option value="processing">{ts("processing")}</option>
            <option value="completed">{ts("completed")}</option>
            <option value="failed">{ts("failed")}</option>
            <option value="unavailable">{ts("unavailable")}</option>
          </select>
        </label>
      </div>

      {visibleSessions.length === 0 ? (
        <p className="rounded-xl border border-dashed border-hairline p-4 text-sm text-ink-mute">
          {ts("noMatchingSessions")}
        </p>
      ) : (
        <div className="space-y-2">
          {visibleSessions.map(session => {
            const status = viewStatus(session)
            const isPolling = SESSION_POLLING_STATUSES.has(session.status)
            const statusLabel =
              status === "failed"
                ? ts("failed")
                : status === "unavailable"
                  ? ts("unavailable")
                  : status === "completed"
                    ? ts("completed")
                    : ts("processing")

            return (
              <Link
                key={session.id}
                href={`/sessions/${session.id}`}
                aria-label={`${session.element_type} ${session.id}`}
                className="block rounded-2xl border border-border p-3 transition-colors hover:bg-accent/30 sm:p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{session.element_type}</p>
                    <p className="mt-1 flex items-center gap-1 text-xs text-ink-mute">
                      <Clock className="h-3 w-3 shrink-0" />
                      {new Date(session.created_at).toLocaleDateString(locale)}
                    </p>
                  </div>
                  <span
                    className="flex shrink-0 items-center gap-1 text-xs text-ink-mute"
                    role="status"
                  >
                    {isPolling && <Loader2 className="h-3 w-3 animate-spin" />}
                    {statusLabel}
                  </span>
                </div>
                {status === "failed" && session.error_message && (
                  <p className="mt-2 text-xs text-destructive">{session.error_message}</p>
                )}
              </Link>
            )
          })}
        </div>
      )}

      {hasNextPage && onLoadMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={isFetchingNextPage}
          className="min-h-11 w-full rounded-xl border border-hairline px-4 py-2 text-sm font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isFetchingNextPage ? ts("loadingSessions") : ts("loadMore")}
        </button>
      )}
    </section>
  )
}
