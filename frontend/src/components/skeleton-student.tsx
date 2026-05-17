import { Skeleton } from "@/components/ui/skeleton"

const METRICS = ["m-1", "m-2", "m-3", "m-4", "m-5", "m-6"] as const
const SESSIONS = ["s-1", "s-2", "s-3"] as const

export function SkeletonStudent() {
  return (
    <div className="space-y-6">
      {/* Student header */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-14 w-14 shrink-0 rounded-full" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {METRICS.map(key => (
          <div key={key} className="rounded-xl border p-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-2 h-6 w-14" />
            <Skeleton className="mt-1 h-2 w-full" />
          </div>
        ))}
      </div>
      {/* Recent sessions */}
      <div className="space-y-3">
        {SESSIONS.map(key => (
          <div key={key} className="flex items-center gap-3 rounded-xl border p-3">
            <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
