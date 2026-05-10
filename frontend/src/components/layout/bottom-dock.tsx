"use client"

import { useQuery } from "@tanstack/react-query"
import { BarChart3, Camera, Music, Newspaper, User, Users } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { z } from "zod"
import { useTranslations } from "@/i18n"
import { apiFetch } from "@/lib/api-client"

const ConnectionListSchema = z.object({
  connections: z.array(z.object({ status: z.string(), connection_type: z.string() })),
})

export function BottomDock() {
  const pathname = usePathname()
  const t = useTranslations("nav")

  const { data: connsData } = useQuery({
    queryKey: ["connections"],
    queryFn: () => apiFetch("/connections", ConnectionListSchema),
  })
  const hasStudents = (connsData?.connections ?? []).some(
    r => r.status === "active" && r.connection_type === "coaching",
  )

  const tabs = [
    { href: "/feed", icon: Newspaper, label: t("feed") },
    { href: "/upload", icon: Camera, label: t("upload") },
    { href: "/choreography", icon: Music, label: t("planner") },
    { href: "/progress", icon: BarChart3, label: t("progress") },
    ...(hasStudents ? [{ href: "/dashboard", icon: Users, label: t("students") }] : []),
    { href: "/profile", icon: User, label: t("profile") },
  ] as const

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`)

  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-hairline bg-background pb-[env(safe-area-inset-bottom)] lg:hidden">
      <div className="flex h-16 items-center justify-around px-2">
        {tabs.map(tab => {
          const Icon = tab.icon
          const active = isActive(tab.href)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              aria-label={tab.label}
              className={`flex flex-col items-center gap-0.5 rounded-md px-4 py-1.5 text-[10px] font-medium transition-colors ${
                active ? "text-ink" : "text-ink-mute"
              }`}
            >
              <Icon className="h-5 w-5" />
              <span>{tab.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
