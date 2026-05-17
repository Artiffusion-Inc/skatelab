"use client"

import { useState } from "react"
import Link from "next/link"
import { StudentCard } from "@/components/coach/student-card"
import { SkeletonCard } from "@/components/skeleton-card"
import { ErrorState } from "@/components/error-state"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { useTranslations } from "@/i18n"
import { useConnections } from "@/lib/api/connections"
import { useSessions } from "@/lib/api/sessions"
import { EmptyState } from "@/components/onboarding"
import { Users } from "lucide-react"
import { CoachViewSwitcher, type ViewMode } from "@/components/layout/coach-view-switcher"
import { SessionCard } from "@/components/session/session-card"

export default function DashboardPage() {
  const connQuery = useConnections()
  const sessionsQuery = useSessions()
  const { isFirstLoad, isError } = usePageStatus([connQuery])
  const ts = useTranslations("students")
  const tc = useTranslations("coach")

  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return "self"
    return (localStorage.getItem("coach_view_mode") as ViewMode) ?? "self"
  })

  const handleModeChange = (next: ViewMode) => {
    setViewMode(next)
    localStorage.setItem("coach_view_mode", next)
  }

  const students = (connQuery.data?.connections ?? []).filter(
    r => r.status === "active" && r.connection_type === "coaching",
  )

  const hasStudents = students.length > 0

  if (isFirstLoad) {
    return (
      <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (isError) return <ErrorState onRetry={() => connQuery.refetch()} />

  if (!hasStudents) {
    return (
      <EmptyState
        icon={<Users className="h-7 w-7 text-primary" />}
        title={ts("noStudents")}
        description={ts("noStudentsHint")}
        primaryAction={{ label: ts("inviteStudent"), href: "/connections" }}
      />
    )
  }

  if (viewMode === "self") {
    const sessions = sessionsQuery.data?.sessions ?? []
    return (
      <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
        <div className="flex items-center justify-between">
          <h1 className="sh-display-md">{tc("viewSelf")}</h1>
          <CoachViewSwitcher mode={viewMode} onModeChange={handleModeChange} />
        </div>
        {sessions.map(s => (
          <SessionCard key={s.id} session={s} />
        ))}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="sh-display-md">{ts("title")}</h1>
        <CoachViewSwitcher mode={viewMode} onModeChange={handleModeChange} />
      </div>
      {students.map((conn, i) => (
        <StudentCard key={conn.id ?? `conn-${i}`} conn={conn} />
      ))}
    </div>
  )
}
