// src/frontend/src/lib/api/sessions.ts
import {
  useMutation,
  useQuery,
  useQueryClient,
  type Query,
  type UseQueryOptions,
} from "@tanstack/react-query"
import { z } from "zod"
import { apiDelete, apiFetch, apiPatch, apiPost } from "@/lib/api-client"

const SessionMetricSchema = z.object({
  id: z.string(),
  metric_name: z.string(),
  metric_value: z.number(),
  is_pr: z.boolean(),
  prev_best: z.number().nullable(),
  reference_value: z.number().nullable(),
  is_in_range: z.boolean().nullable(),
  unit: z.string().optional(),
})

// Analysis data schemas (Task 6, 2026-04-16)
const PoseDataSchema = z.object({
  frames: z.array(z.number()),
  poses: z.array(z.array(z.array(z.number()))), // [frame][keypoint][x,y,conf]
  fps: z.number(),
})

const FrameMetricsSchema = z.object({
  knee_angles_r: z.array(z.number().nullable()),
  knee_angles_l: z.array(z.number().nullable()),
  hip_angles_r: z.array(z.number().nullable()),
  hip_angles_l: z.array(z.number().nullable()),
  trunk_lean: z.array(z.number().nullable()),
  com_height: z.array(z.number().nullable()),
})

const PhaseFrameSchema = z.object({
  frame: z.number(),
  timestamp: z.number().optional(),
})

const PhasesDataSchema = z.object({
  takeoff: PhaseFrameSchema,
  peak: PhaseFrameSchema,
  landing: PhaseFrameSchema,
})

const ElementSegmentSchema = z.object({
  id: z.string(),
  element_type: z.string(),
  element_name: z.string().nullable().optional(),
  start_frame: z.number(),
  end_frame: z.number(),
  confidence: z.number(),
  phases_json: PhasesDataSchema.nullable().optional(),
})

const TimelineDataSchema = z.object({
  segments: z.array(ElementSegmentSchema),
  segmentation_confidence: z.number().nullable().optional(),
  segmentation_status: z.string().default("pending"),
})

const SessionSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  element_type: z.string(),
  video_key: z.string().nullable().optional(),
  video_url: z.string().nullable(),
  processed_video_key: z.string().nullable().optional(),
  processed_video_url: z.string().nullable(),
  poses_url: z.string().optional().nullable(), // Deprecated
  csv_url: z.string().optional().nullable(), // Deprecated
  pose_data: PoseDataSchema.optional().nullable(), // New
  frame_metrics: FrameMetricsSchema.optional().nullable(), // New
  status: z.string(),
  error_message: z.string().nullable(),
  phases: PhasesDataSchema.optional().nullable(), // Updated type
  recommendations: z.array(z.string()).nullable(),
  overall_score: z.number().nullable(),
  process_task_id: z.string().nullable().optional(),
  imu_left_key: z.string().nullable().optional(),
  imu_right_key: z.string().nullable().optional(),
  manifest_key: z.string().nullable().optional(),
  created_at: z.string(),
  processed_at: z.string().nullable(),
  metrics: z.array(SessionMetricSchema),
  timeline: TimelineDataSchema.optional().nullable(),
  segmentation_status: z.string().default("pending"),
})

const SessionListSchema = z.object({ sessions: z.array(SessionSchema), total: z.number() })

type Session = z.infer<typeof SessionSchema>

/**
 * Session statuses that count as "in progress" — the session-detail page renders a
 * processing banner for these, and useSession must poll (refetch) while one is active
 * or the page freezes on e.g. "queued" right after upload. Single source of truth,
 * shared by the hook and the page. #457
 */
export const SESSION_POLLING_STATUSES = new Set([
  "queued",
  "uploading",
  "running",
  "pending",
  "processing",
])

export function useSessions(userId?: string, elementType?: string) {
  const params = new URLSearchParams()
  if (userId) params.set("user_id", userId)
  if (elementType) params.set("element_type", elementType)
  return useQuery({
    queryKey: ["sessions", userId, elementType],
    queryFn: () => apiFetch(`/sessions?${params.toString()}`, SessionListSchema),
  })
}

export function useSession(id: string, opts?: { refetchInterval?: number | false }) {
  return useQuery<Session, Error, Session>({
    queryKey: ["session", id],
    queryFn: () => apiFetch(`/sessions/${id}`, SessionSchema),
    enabled: !!id,
    refetchInterval: query => {
      const data = query.state.data
      // Poll while the session is in any in-progress status. This must match the
      // session-detail page's banner set — the page shows a "processing" banner for
      // these statuses, so the hook must refetch or the page freezes (e.g. status
      // "queued" right after upload previously polled never). Single source of
      // truth: SESSION_POLLING_STATUSES (shared with the page). #457
      if (data?.status && SESSION_POLLING_STATUSES.has(data.status)) return 5000
      if (data?.segmentation_status === "pending") return 5000
      if (opts?.refetchInterval !== undefined) return opts.refetchInterval
      return false
    },
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      element_type: string
      video_key?: string
      imu_left_key?: string
      imu_right_key?: string
      manifest_key?: string
    }) => apiPost("/sessions", SessionSchema, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] })
      qc.invalidateQueries({ queryKey: ["trend"] })
      qc.invalidateQueries({ queryKey: ["diagnostics"] })
    },
  })
}

export function usePatchSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      apiPatch(`/sessions/${id}`, SessionSchema, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["session", id] })
      qc.invalidateQueries({ queryKey: ["sessions"] })
    },
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/sessions/${id}`),
    onSuccess: (_, id) => {
      // Remove the detail key for the deleted id — the session no longer exists, so
      // there is nothing to refetch (invalidate would re-fetch and 404; the orphaned
      // completed-session object would otherwise sit in cache and resurface on
      // browser-back within gcTime). removeQueries drops it so the next mount fetches
      // fresh. The list key is invalidated as before. #456
      qc.removeQueries({ queryKey: ["session", id] })
      qc.invalidateQueries({ queryKey: ["sessions"] })
    },
  })
}

export function useBulkDeleteSessions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => apiDelete(`/sessions/bulk?ids=${ids.join(",")}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  })
}

export function useRetrySession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ sessionId, videoKey }: { sessionId: string; videoKey: string }) => {
      await apiPost("/process/queue", z.any(), {
        video_key: videoKey,
        person_click: { x: 0.5, y: 0.5 },
      })
      return apiPatch(`/sessions/${sessionId}`, SessionSchema, { status: "queued" })
    },
    onSuccess: (_, { sessionId }) => {
      qc.invalidateQueries({ queryKey: ["session", sessionId] })
      qc.invalidateQueries({ queryKey: ["sessions"] })
    },
  })
}
