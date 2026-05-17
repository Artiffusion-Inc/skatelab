import { Skeleton } from "@/components/ui/skeleton"

const STATS = ["stat-sessions", "stat-prs", "stat-avg", "stat-streak"] as const
const ACTIVITY = ["act-1", "act-2", "act-3"] as const

export function SkeletonProfile() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-16 w-16 shrink-0 rounded-full" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-3">
        {STATS.map(key => (
          <div key={key} className="rounded-xl border p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="mt-2 h-6 w-12" />
          </div>
        ))}
      </div>
      {/* Recent activity */}
      <div className="space-y-3">
        {ACTIVITY.map(key => (
          <div key={key} className="flex items-center gap-3 rounded-xl border p-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
            <Skeleton className="h-5 w-12 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  )
}
