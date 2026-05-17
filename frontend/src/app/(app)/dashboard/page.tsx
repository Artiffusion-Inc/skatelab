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
import { DemoBadge } from "@/components/demo/demo-badge"
import { useAuth } from "@/components/auth-provider"
import { SANDBOX_STUDENTS } from "@/components/coach/coach-sandbox-data"
import { Button } from "@/components/ui/button"

export default function DashboardPage() {
  const connQuery = useConnections()
  const sessionsQuery = useSessions()
  const { user } = useAuth()
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
  const isCoachWithNoStudents = !hasStudents && user?.onboarding_role === "coach"

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

  if (!hasStudents && !isCoachWithNoStudents) {
    return (
      <EmptyState
        icon={<Users className="h-7 w-7 text-primary" />}
        title={ts("noStudents")}
        description={ts("noStudentsHint")}
        primaryAction={{ label: ts("inviteStudent"), href: "/connections" }}
      />
    )
  }

  // Coach sandbox: show demo students when coach has no real ones yet
  if (isCoachWithNoStudents) {
    return (
      <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
        <div className="flex items-center gap-2">
          <h1 className="sh-display-md">{ts("title")}</h1>
          <DemoBadge />
        </div>
        {SANDBOX_STUDENTS.map(s => (
          <div key={s.id} className="rounded-2xl border border-border p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
                {s.display_name[0]}
              </div>
              <div className="flex-1">
                <p className="font-medium text-sm">{s.display_name}</p>
                <p className="text-xs text-muted-foreground">
                  {s.sessions_this_week} {ts("progress").toLowerCase()} &middot; {s.latest_element}{" "}
                  &middot; {s.latest_score}/10
                </p>
              </div>
            </div>
          </div>
        ))}
        <Button asChild variant="outline" className="w-full">
          <Link href="/connections">{tc("inviteRealStudents")}</Link>
        </Button>
      </div>
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
