"use client"

import { useTranslations } from "@/i18n"
import {
  useSessionScores,
  useSessionPhases,
  useUserLevel,
  useUserSkills,
  useGenerateTrainingPlan,
} from "@/lib/api/analyzer"
import { ScoreBreakdown } from "@/components/analysis/score-breakdown"
import { PhaseTimelineExtended } from "@/components/analysis/phase-timeline-extended"
import { GamificationPanel } from "@/components/gamification/gamification-panel"
import { TrainingPlanComponent } from "@/components/gamification/training-plan"
import { mockUserLevel, mockSkills } from "@/lib/mocks/skating-analyzer"
import { useAuth } from "@/components/auth-provider"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

interface Props {
  sessionId: string
  totalFrames: number
}

export function AnalyzerTab({ sessionId, totalFrames }: Props) {
  const t = useTranslations("analysis")
  const { user } = useAuth()
  const userId = user?.id ?? ""

  const scoresQuery = useSessionScores(sessionId)
  const phasesQuery = useSessionPhases(sessionId)
  const levelQuery = useUserLevel(userId)
  const skillsQuery = useUserSkills(userId)
  const generatePlan = useGenerateTrainingPlan(sessionId)

  const isLoading = scoresQuery.isLoading || phasesQuery.isLoading

  return (
    <div className="space-y-4">
      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : scoresQuery.data ? (
        <ScoreBreakdown score={scoresQuery.data} />
      ) : null}

      {phasesQuery.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : phasesQuery.data ? (
        <PhaseTimelineExtended result={phasesQuery.data} totalFrames={totalFrames} />
      ) : null}

      {levelQuery.data ? (
        <GamificationPanel level={levelQuery.data} skills={skillsQuery.data ?? mockSkills} />
      ) : (
        <GamificationPanel level={mockUserLevel} skills={mockSkills} />
      )}

      {generatePlan.data ? (
        <TrainingPlanComponent plan={generatePlan.data} />
      ) : (
        <div className="space-y-2">
          <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending}>
            {generatePlan.isPending ? t("generatingPlan") : t("generatePlan")}
          </Button>
          {generatePlan.isError ? (
            <p className="text-sm text-destructive">{t("planError")}</p>
          ) : null}
        </div>
      )}
    </div>
  )
}
