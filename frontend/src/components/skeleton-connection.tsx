import { Skeleton } from "@/components/ui/skeleton"

const ROWS = ["conn-1", "conn-2", "conn-3", "conn-4"] as const

export function SkeletonConnection() {
  return (
    <div className="space-y-4">
      {ROWS.map(key => (
        <div key={key} className="flex items-center gap-3 rounded-xl border p-4">
          <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-24" />
          </div>
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      ))}
    </div>
  )
}
