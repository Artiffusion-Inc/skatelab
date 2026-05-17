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

export function useProcessingSessions() {
  const { user } = useAuth()

  const { data } = useQuery({
    queryKey: ["sessions", user?.id, "processing"],
    queryFn: () =>
      apiFetch("/sessions?status=processing", ProcessingSessionListSchema),
    enabled: !!user,
    refetchInterval: 30_000,
  })

  const processingCount = data?.sessions.length ?? 0
  const hasProcessing = processingCount > 0

  return { hasProcessing, processingCount }
}
