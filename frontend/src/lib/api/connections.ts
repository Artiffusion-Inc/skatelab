import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { apiFetch, apiPost } from "@/lib/api-client"

export const ConnectionSchema = z.object({
  id: z.string(),
  from_user_id: z.string(),
  to_user_id: z.string(),
  connection_type: z.enum(["coaching", "choreography"]),
  status: z.enum(["invited", "active", "ended"]),
  initiated_by: z.string().nullable(),
  created_at: z.string(),
  ended_at: z.string().nullable(),
  from_user_name: z.string().nullable(),
  to_user_name: z.string().nullable(),
})

export const ConnectionListSchema = z.object({
  connections: z.array(ConnectionSchema),
  total: z.number().default(0),
})

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: () => apiFetch("/connections", ConnectionListSchema),
  })
}

export function usePendingConnections() {
  return useQuery({
    queryKey: ["connections", "pending"],
    queryFn: () => apiFetch("/connections/pending", ConnectionListSchema),
  })
}

export function useInviteConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { to_user_email: string; connection_type: "coaching" | "choreography" }) =>
      apiPost("/connections/invite", ConnectionSchema, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  })
}

export function useAcceptConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connId: string) => apiPost(`/connections/${connId}/accept`, ConnectionSchema, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] })
      qc.invalidateQueries({ queryKey: ["sessions"] })
      qc.invalidateQueries({ queryKey: ["session"] })
    },
  })
}

export function useEndConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connId: string) => apiPost(`/connections/${connId}/end`, ConnectionSchema, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] })
      qc.invalidateQueries({ queryKey: ["sessions"] })
      qc.invalidateQueries({ queryKey: ["session"] })
    },
  })
}
