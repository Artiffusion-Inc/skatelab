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

export function AppNav() {
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
  ] as const

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`)

  return (
    <nav className="flex items-center gap-0.5">
      {/* Desktop tabs */}
      <div className="hidden items-center gap-0.5 md:flex">
        {tabs.map(tab => {
          const Icon = tab.icon
          const active = isActive(tab.href)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none ${
                active ? "bg-muted text-ink" : "text-ink-mute hover:text-ink hover:bg-muted/50"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </Link>
          )
        })}
      </div>

      {/* Right-side actions */}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Link
          href="/profile"
          aria-label={t("profile")}
          className={`flex items-center gap-1.5 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted hover:text-ink focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none ${
            isActive("/profile") ? "text-ink bg-muted" : "text-ink-mute"
          }`}
        >
          <User className="h-4 w-4" />
        </Link>
      </div>
    </nav>
  )
}
