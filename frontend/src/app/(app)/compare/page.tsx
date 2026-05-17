"use client"

import { BarChart3 } from "lucide-react"
import { SessionComparison } from "@/components/session/session-comparison"
import { ErrorState } from "@/components/error-state"
import { SkeletonCompare } from "@/components/skeleton-compare"
import { EmptyState } from "@/components/onboarding"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { useSessions } from "@/lib/api/sessions"
import { useTranslations } from "@/i18n"

export default function ComparePage() {
  const t = useTranslations("compare")
  const tEmpty = useTranslations("emptyStates")
  const sessionsQuery = useSessions()
  const { isFirstLoad, isError } = usePageStatus([sessionsQuery])

  if (isFirstLoad) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <SkeletonCompare />
      </div>
    )
  }

  if (isError) return <ErrorState onRetry={() => sessionsQuery.refetch()} />

  const sessions = sessionsQuery.data?.sessions ?? []

  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={<BarChart3 className="h-7 w-7 text-primary" />}
        title={tEmpty("compareTitle")}
        description={tEmpty("compareDesc")}
      />
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <SessionComparison />
    </div>
  )
}
