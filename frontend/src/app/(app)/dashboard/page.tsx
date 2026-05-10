"use client"

import Link from "next/link"
import { StudentCard } from "@/components/coach/student-card"
import { useTranslations } from "@/i18n"
import { useConnections } from "@/lib/api/connections"
import { EmptyState } from "@/components/onboarding"
import { Users } from "lucide-react"

export default function DashboardPage() {
  const { data, isLoading } = useConnections()
  const tc = useTranslations("common")
  const ts = useTranslations("students")

  const students = (data?.connections ?? []).filter(
    r => r.status === "active" && r.connection_type === "coaching",
  )

  if (isLoading)
    return <div className="py-20 text-center text-ink-mute">{tc("loading")}</div>

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
