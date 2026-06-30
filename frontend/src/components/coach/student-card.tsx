"use client"

import { Clock } from "lucide-react"
import Link from "next/link"
import { useLocale, useTranslations } from "@/i18n"
import type { Connection } from "@/types"

export function StudentCard({ conn }: { conn: Connection }) {
  const t = useTranslations("coach")
  const locale = useLocale()

  return (
    <Link href={`/students/${conn.to_user_id}`} className="block">
      <div className="rounded-2xl border border-border p-4 hover:bg-accent/30 transition-colors">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
            {/* `||` (not `??`) — empty string is falsy-but-not-nullish, so `??`
               would return ""[0]=undefined → .toUpperCase() throws (#477). */}
            {(conn.to_user_name || "?")[0].toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-sm">{conn.to_user_name || t("studentFallback")}</p>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {new Date(conn.created_at).toLocaleDateString(locale)}
            </p>
          </div>
        </div>
      </div>
    </Link>
  )
}
