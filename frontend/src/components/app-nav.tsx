"use client"

import { useQuery } from "@tanstack/react-query"
import { BarChart3, Music, Newspaper, User, Users } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { z } from "zod"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
    { href: "/feed", icon: Newspaper, label: t("sessions") },
    { href: "/progress", icon: BarChart3, label: t("progress") },
    { href: "/choreography", icon: Music, label: t("programs") },
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

      {/* Right-side profile dropdown */}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={t("profile")}
              className={`flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-sm transition-colors hover:bg-muted hover:text-ink focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none ${
                isActive("/profile") || isActive("/connections") || isActive("/settings")
                  ? "text-ink bg-muted"
                  : "text-ink-mute"
              }`}
            >
              <User className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <Link href="/profile">{t("profile")}</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/connections">{t("connections")}</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/settings">{t("settings")}</Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  )
}
