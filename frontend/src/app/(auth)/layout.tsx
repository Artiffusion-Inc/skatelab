import { Activity } from "lucide-react"
import Link from "next/link"
import { getTranslations } from "next-intl/server"

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("app")

  return (
    <div className="flex min-h-[dvh] flex-col">
      <header className="bg-primary pt-[env(safe-area-inset-top)]">
        <div className="flex h-[52px] items-center px-6">
          <Link href="/" className="flex items-center gap-2 font-semibold text-primary-foreground">
            <Activity className="h-5 w-5 text-surface-violet-soft" />
            <span>{t("title")}</span>
          </Link>
        </div>
      </header>
      <div className="flex flex-1 items-center justify-center bg-background px-6 py-8">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  )
}
