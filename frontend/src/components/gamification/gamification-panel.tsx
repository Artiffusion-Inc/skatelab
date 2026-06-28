"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { useTranslations } from "@/i18n"
import type { UserLevel, SkillItem } from "@/types"
import { Lock, Trophy, Star } from "lucide-react"

interface Props {
  level: UserLevel
  skills: SkillItem[]
}

function tierIcon(tier: SkillItem["tier"]) {
  switch (tier) {
    case "bronze":
      return "🥉"
    case "silver":
      return "🥈"
    case "gold":
      return "🥇"
  }
}

export function GamificationPanel({ level, skills }: Props) {
  const t = useTranslations("gamification")
  const xpProgress = (level.total_xp / level.xp_to_next) * 100

  const grouped = skills.reduce(
    (acc, skill) => {
      acc[skill.category].push(skill)
      return acc
    },
    { jumps: [] as SkillItem[], spins: [] as SkillItem[], control: [] as SkillItem[] },
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5 text-primary" />
          {t("level")} {level.level} — {level.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* XP Bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-sm">
            <span>{t("xp")}</span>
            <span>
              {level.total_xp} / {level.xp_to_next} XP
            </span>
          </div>
          <Progress value={Math.min(xpProgress, 100)} className="h-3" />
        </div>

        {/* Skills Grid */}
        <div className="grid grid-cols-3 gap-3">
          {(["jumps", "spins", "control"] as const).map(category => (
            <div key={category} className="space-y-2">
              <div className="text-xs font-medium text-center capitalize">
                {t(category)}
              </div>
              {grouped[category].map(skill => (
                <div
                  key={skill.id}
                  className={`relative flex flex-col items-center gap-1 rounded-lg border p-2 text-center transition-opacity ${
                    skill.unlocked
                      ? "bg-primary/5 border-primary/20"
                      : "bg-muted/50 border-muted opacity-60"
                  }`}
                  title={
                    skill.unlocked
                      ? `${t("unlockedAt")} ${skill.unlocked_at}`
                      : `${t("requires")} ${skill.label_ru}`
                  }
                >
                  <span className="text-lg">{tierIcon(skill.tier)}</span>
                  {/* TODO #407: backend should provide label_en; using label_ru as fallback */}
                  <span className="text-[10px] leading-tight">{skill.label_ru}</span>
                  {skill.unlocked ? (
                    <Star className="h-3 w-3 text-primary fill-primary" />
                  ) : (
                    <Lock className="h-3 w-3 text-muted-foreground" />
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
