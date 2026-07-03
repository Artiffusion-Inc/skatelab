import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api-client"
import { useAuth } from "@/components/auth-provider"
import { z } from "zod"

const ProcessingSessionSchema = z.object({
  id: z.string(),
  status: z.string(),
})

const ProcessingSessionListSchema = z.object({
  sessions: z.array(ProcessingSessionSchema),
  total: z.number(),
})

// #490: client-side filter for "still processing" statuses. The backend
// list_sessions ignores the `?status=processing` query param, so we filter
// locally. The "still processing" statuses are "uploading" (in the queue)
// and "processing" (the worker is running). All other statuses
// ("done", "failed", "partial", "completed", "deleted") are terminal.
const POLLING_STATUSES = new Set(["uploading", "processing"])

export function useProcessingSessions() {
  const { user } = useAuth()

  const { data } = useQuery({
    queryKey: ["sessions", user?.id, "processing"],
    queryFn: () => apiFetch("/sessions?status=processing", ProcessingSessionListSchema),
    enabled: !!user,
    // #490: stop polling when no sessions are processing. Static
    // `refetchInterval: 30_000` kept firing for the component lifetime
    // even when all sessions were terminal (battery / bandwidth
    // waste on mobile). Use the predicate form — return `false` to
    // stop, `30_000` to keep polling. Same fix pattern as the
    // #457 useSession sibling.
    refetchInterval: query => {
      const sessions = query.state.data?.sessions ?? []
      const hasProcessing = sessions.some(s => POLLING_STATUSES.has(s.status))
      return hasProcessing ? 30_000 : false
    },
  })

  // #490: client-side filter — backend's `?status=processing` query
  // param is silently ignored, so all non-deleted sessions are
  // returned. Filter locally to only the "still processing" statuses.
  const processingSessions = (data?.sessions ?? []).filter(s => POLLING_STATUSES.has(s.status))
  const processingCount = processingSessions.length
  const hasProcessing = processingCount > 0

  return { hasProcessing, processingCount }
}
