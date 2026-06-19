import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { apiFetch, apiPost } from "@/lib/api-client"
import type {
  MultiDimensionalScore,
  PhaseDetectionResult,
  UserLevel,
  SkillItem,
  TrainingPlan,
} from "@/types"

// --- Schemas ---

const SubScoreSchema = z.object({
  name: z.string(),
  label_ru: z.string(),
  value: z.number(),
  confidence: z.number(),
  contributing_metrics: z.array(z.string()),
})

const SessionScoreSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  subscores: z.array(SubScoreSchema),
  overall: z.number(),
  data_quality: z.string(),
  skeleton_reliability: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})

const PhaseExtendedSchema = z.object({
  name: z.string(),
  start_frame: z.number(),
  end_frame: z.number(),
  start_time: z.number(),
  end_time: z.number(),
  confidence: z.number(),
  detection_method: z.string(),
})

const SessionPhaseSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  phases: z.array(PhaseExtendedSchema),
  overall_confidence: z.number(),
  element_type: z.string().nullable(),
  fallback_used: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

const UserLevelSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  level: z.number(),
  total_xp: z.number(),
  xp_to_next: z.number(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})

const SkillProgressSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  skill_id: z.string(),
  category: z.string(),
  tier: z.string(),
  unlocked: z.boolean(),
  unlocked_at: z.string().nullable(),
  consecutive_sessions: z.number(),
  best_score: z.number(),
  xp_reward: z.number(),
})

const TrainingPlanItemSchema = z.object({
  id: z.string(),
  priority: z.number(),
  label_ru: z.string(),
  description_ru: z.string(),
  completed: z.boolean(),
})

const TrainingPlanSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  session_id: z.string().nullable(),
  items: z.array(TrainingPlanItemSchema),
  generated_at: z.string(),
  completed: z.boolean(),
  focus_subscore: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})

// --- Adapters: API shape → component types ---

function toMultiDimensionalScore(s: z.infer<typeof SessionScoreSchema>): MultiDimensionalScore {
  return {
    subscores: s.subscores.map(ss => ({
      name: ss.name,
      label_ru: ss.label_ru,
      value: ss.value,
      confidence: ss.confidence,
      contributing_metrics: ss.contributing_metrics,
    })),
    overall: s.overall,
    data_quality: s.data_quality as MultiDimensionalScore["data_quality"],
    skeleton_reliability: s.skeleton_reliability as MultiDimensionalScore["skeleton_reliability"],
  }
}

function toPhaseDetectionResult(s: z.infer<typeof SessionPhaseSchema>): PhaseDetectionResult {
  return {
    phases: s.phases.map(p => ({
      name: p.name as PhaseDetectionResult["phases"][number]["name"],
      start_frame: p.start_frame,
      end_frame: p.end_frame,
      start_time: p.start_time,
      end_time: p.end_time,
      confidence: p.confidence,
      detection_method:
        p.detection_method as PhaseDetectionResult["phases"][number]["detection_method"],
    })),
    overall_confidence: s.overall_confidence,
    element_type: s.element_type,
    fallback_used: s.fallback_used,
  }
}

function toSkillItems(skills: z.infer<typeof SkillProgressSchema>[]): SkillItem[] {
  return skills.map(s => ({
    id: s.skill_id,
    category: s.category as SkillItem["category"],
    tier: s.tier as SkillItem["tier"],
    label_ru: s.skill_id, // backend doesn't store label_ru; use skill_id as fallback
    unlocked: s.unlocked,
    unlocked_at: s.unlocked_at,
    consecutive_sessions: s.consecutive_sessions,
    best_score: s.best_score,
    xp_reward: s.xp_reward,
  }))
}

function toTrainingPlan(s: z.infer<typeof TrainingPlanSchema>): TrainingPlan {
  return {
    items: s.items.map(i => ({
      id: i.id,
      priority: i.priority,
      label_ru: i.label_ru,
      description_ru: i.description_ru,
      completed: i.completed,
    })),
    generated_at: s.generated_at,
    completed: s.completed,
    focus_subscore: s.focus_subscore,
  }
}

// --- Hooks ---

export function useSessionScores(sessionId: string) {
  return useQuery<MultiDimensionalScore, Error>({
    queryKey: ["analyzer", "scores", sessionId],
    queryFn: async () =>
      toMultiDimensionalScore(await apiFetch(`/sessions/${sessionId}/scores`, SessionScoreSchema)),
    enabled: !!sessionId,
  })
}

export function useSessionPhases(sessionId: string) {
  return useQuery<PhaseDetectionResult, Error>({
    queryKey: ["analyzer", "phases", sessionId],
    queryFn: async () =>
      toPhaseDetectionResult(await apiFetch(`/sessions/${sessionId}/phases`, SessionPhaseSchema)),
    enabled: !!sessionId,
  })
}

export function useUserLevel(userId: string) {
  return useQuery<UserLevel, Error>({
    queryKey: ["analyzer", "level", userId],
    queryFn: async () => {
      const data = await apiFetch(`/users/${userId}/level`, UserLevelSchema)
      return {
        level: data.level,
        total_xp: data.total_xp,
        xp_to_next: data.xp_to_next,
        title: data.title,
      }
    },
    enabled: !!userId,
  })
}

export function useUserSkills(userId: string) {
  return useQuery<SkillItem[], Error>({
    queryKey: ["analyzer", "skills", userId],
    queryFn: async () =>
      toSkillItems(await apiFetch(`/users/${userId}/skills`, z.array(SkillProgressSchema))),
    enabled: !!userId,
  })
}

export function useGenerateTrainingPlan(sessionId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const data = await apiPost("/training-plans/generate", TrainingPlanSchema, {
        session_id: sessionId,
      })
      return toTrainingPlan(data)
    },
    onSuccess: () => {
      if (sessionId) qc.invalidateQueries({ queryKey: ["analyzer", "plan", sessionId] })
    },
  })
}

export function useTrainingPlan(planId: string | undefined) {
  return useQuery<TrainingPlan, Error>({
    queryKey: ["analyzer", "plan", planId],
    queryFn: async () =>
      toTrainingPlan(await apiFetch(`/training-plans/${planId}`, TrainingPlanSchema)),
    enabled: !!planId,
  })
}
