"use client"

import Link from "next/link"
import { TrendingUp, Minus, TrendingDown, Circle } from "lucide-react"
import { useTranslations } from "@/i18n"

type HealthStatus = "improving" | "stagnant" | "declining" | "no_data"

interface ElementCardProps {
  elementId: string
  health: HealthStatus
  lastSessionDate?: string
  findingCount?: number
}

const healthConfig: Record<HealthStatus, { icon: typeof TrendingUp; className: string }> = {
  improving: { icon: TrendingUp, className: "text-green-600" },
  stagnant: { icon: Minus, className: "text-yellow-600" },
  declining: { icon: TrendingDown, className: "text-red-600" },
  no_data: { icon: Circle, className: "text-gray-400" },
}

export function ElementCard({
  elementId,
  health,
  lastSessionDate,
  findingCount,
}: ElementCardProps) {
  const te = useTranslations("elements")
  const tp = useTranslations("progress")
  const config = healthConfig[health]
  const Icon = config.icon

  return (
    <Link
      href={`/progress?element=${elementId}`}
      className="flex items-center gap-3 rounded-2xl border border-hairline p-3 transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Icon
        className={`h-5 w-5 shrink-0 ${config.className}`}
        aria-label={tp(`health.${health}`)}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{te(elementId)}</p>
        {lastSessionDate && (
          <p className="text-xs text-ink-mute">
            {new Date(lastSessionDate).toLocaleDateString("ru-RU")}
          </p>
        )}
      </div>
      {findingCount && findingCount > 0 && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-yellow-500/10 text-[10px] font-bold text-yellow-600">
          {findingCount}
        </span>
      )}
    </Link>
  )
}

export type { HealthStatus }
