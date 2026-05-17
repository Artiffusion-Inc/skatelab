"use client"

import { ActivityTabs } from "@/components/profile/activity-tabs"
import { PersonalRecords } from "@/components/profile/personal-records"
import { ProfileHero } from "@/components/profile/profile-hero"
import { RecentActivity } from "@/components/profile/recent-activity"
import { SettingsSheet } from "@/components/profile/settings-sheet"
import { StatsSummary } from "@/components/profile/stats-summary"
import { ErrorState } from "@/components/error-state"
import { SkeletonProfile } from "@/components/skeleton-profile"
import { usePageStatus } from "@/lib/hooks/use-page-status"
import { usePRs } from "@/lib/api/metrics"
import { useSessions } from "@/lib/api/sessions"

export default function ProfilePage() {
  const sessionsQ = useSessions()
  const prsQ = usePRs()
  const { isFirstLoad, isError } = usePageStatus([sessionsQ, prsQ])

  if (isFirstLoad) return <SkeletonProfile />
  if (isError)
    return (
      <ErrorState
        onRetry={() => {
          sessionsQ.refetch()
          prsQ.refetch()
        }}
      />
    )

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 py-4">
      <ProfileHero />
      <StatsSummary />
      <ActivityTabs activityContent={<RecentActivity />} recordsContent={<PersonalRecords />} />
      <SettingsSheet />
    </div>
  )
}
