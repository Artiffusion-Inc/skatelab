"use client"

import Link from "next/link"
import { StudentCard } from "@/components/coach/student-card"
import { SkeletonCard } from "@/components/skeleton-card"
import { ErrorState } from "@/components/error-state"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { useTranslations } from "@/i18n"
import { useConnections } from "@/lib/api/connections"
import { EmptyState } from "@/components/onboarding"
import { Users } from "lucide-react"

export default function DashboardPage() {
  const query = useConnections()
  const { isFirstLoad, isError } = usePageStatus([query])
  const ts = useTranslations("students")

  const students = (query.data?.connections ?? []).filter(
    r => r.status === "active" && r.connection_type === "coaching",
  )

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

  if (!students.length) {
    return (
      <EmptyState
        icon={<Users className="h-7 w-7 text-primary" />}
        title={ts("noStudents")}
        description={ts("noStudentsHint")}
        primaryAction={{ label: ts("inviteStudent"), href: "/connections" }}
      />
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-3 sm:max-w-3xl">
      <h1 className="sh-display-md">{ts("title")}</h1>
      {students.map((conn, i) => (
        <StudentCard key={conn.id ?? `conn-${i}`} conn={conn} />
      ))}
    </div>
  )
}
