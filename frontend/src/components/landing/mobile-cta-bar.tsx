"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"

interface MobileCTABarProps {
  hidden: boolean
}

export function MobileCTABar({ hidden }: MobileCTABarProps) {
  const t = useTranslations("landing")

  if (hidden) return null

  return (
    <aside
      aria-label={t("ctaPrimary")}
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-hairline bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <div className="flex items-center justify-center px-4 py-3">
        <Button size="lg" className="min-h-[44px] w-full max-w-md" asChild>
          <a href="https://t.me/SkateLabPro" target="_blank" rel="noopener noreferrer">
            {t("ctaPrimary")}
          </a>
        </Button>
      </div>
    </aside>
  )
}
