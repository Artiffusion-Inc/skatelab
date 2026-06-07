"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import type { TrainingPlan } from "@/types"
import { Dumbbell, CheckCircle2 } from "lucide-react"

interface Props {
  plan: TrainingPlan
  onToggleItem?: (itemId: string, completed: boolean) => void
}

function priorityColor(priority: number): string {
  switch (priority) {
    case 1: return "bg-red-100 text-red-800 border-red-200"
    case 2: return "bg-orange-100 text-orange-800 border-orange-200"
    case 3: return "bg-yellow-100 text-yellow-800 border-yellow-200"
    default: return "bg-blue-100 text-blue-800 border-blue-200"
  }
}

export function TrainingPlanComponent({ plan, onToggleItem }: Props) {
  const completed = plan.items.filter(i => i.completed).length
  const total = plan.items.length

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <Dumbbell className="h-5 w-5 text-primary" />
          План тренировки
          <span className="text-sm text-muted-foreground font-normal">
            ({completed}/{total})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {plan.items.map((item) => (
          <div
            key={item.id}
            className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
              item.completed ? "bg-muted/50 border-muted" : "bg-background border-border"
            }`}
          >
            <Checkbox
              checked={item.completed}
              onCheckedChange={(checked) =>
                onToggleItem?.(item.id, checked === true)
              }
              className="mt-0.5"
            />
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium ${priorityColor(item.priority)}`}
                >
                  #{item.priority}
                </span>
                <span className={`text-sm font-medium ${item.completed ? "line-through text-muted-foreground" : ""}`}>
                  {item.label_ru}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {item.description_ru}
              </p>
            </div>
            {item.completed && (
              <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
