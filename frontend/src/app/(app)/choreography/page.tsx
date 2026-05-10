"use client"

import { Music, Plus } from "lucide-react"
import Link from "next/link"
import { useTranslations } from "@/i18n"
import { usePrograms } from "@/lib/api/choreography"
import { EmptyState } from "@/components/onboarding"

export default function ChoreographyPage() {
  const t = useTranslations("choreography")
  const tc = useTranslations("common")
  const { data, isLoading } = usePrograms()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-ink-mute">{tc("loading")}</div>
    )
  }

  if (!data?.programs.length) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-6 sm:max-w-3xl">
        <div className="flex items-center justify-between">
          <h1 className="sh-heading-lg">{t("title")}</h1>
          <Link
            href="/choreography/new"
            className="flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            {t("newProgram")}
          </Link>
        </div>
        <EmptyState
          icon={<Music className="h-7 w-7 text-primary" />}
          title={t("noPrograms")}
          description={t("newProgram")}
          primaryAction={{ label: t("newProgram"), href: "/choreography/new" }}
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 px-4 py-6 sm:max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="sh-heading-lg">{t("title")}</h1>
        <Link
          href="/choreography/new"
          className="flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          {t("newProgram")}
        </Link>
      </div>
      <div className="space-y-2">
        {data.programs.map(p => (
          <Link
            key={p.id}
            href={`/choreography/programs/${p.id}`}
            className="block rounded-2xl border border-hairline p-3 transition-colors hover:bg-accent/30"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">{p.title || `${p.segment} — ${p.discipline}`}</p>
                <p className="text-xs text-ink-mute">{p.season.replace("_", "/")}</p>
              </div>
              {p.estimated_total !== null && (
                <span className="text-sm font-bold">{p.estimated_total.toFixed(2)}</span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
