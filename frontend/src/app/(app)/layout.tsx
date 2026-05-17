import { Activity } from "lucide-react"
import { cookies } from "next/headers"
import Link from "next/link"
import { redirect } from "next/navigation"
import { getTranslations } from "next-intl/server"
import { AppNav } from "@/components/app-nav"
import { BottomDock } from "@/components/layout/bottom-dock"
import { OnboardingGate } from "@/components/onboarding/onboarding-gate"

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("app")

  const hasAuth = (await cookies()).get("sb_auth")?.value
  if (!hasAuth) redirect("/login")

  return (
    <OnboardingGate>
      <div className="flex min-h-screen flex-col">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-foreground focus:ring-2 focus:ring-ring"
        >
          Перейти к содержимому
        </a>
        <header className="sticky top-0 z-50 border-b border-hairline bg-background">
          <div className="mx-auto flex h-[52px] max-w-5xl items-center justify-between px-6">
            <Link href="/feed" className="flex items-center gap-2 font-semibold text-ink">
              <Activity className="h-5 w-5 text-primary" />
              <span className="hidden sm:inline">{t("title")}</span>
            </Link>
            <AppNav />
          </div>
        </header>
        <main
          id="main-content"
          className="mx-auto w-full max-w-5xl flex-1 px-6 py-4 pb-24 sm:py-6 sm:pb-8"
        >
          {children}
        </main>
        <BottomDock />
      </div>
    </OnboardingGate>
  )
}
