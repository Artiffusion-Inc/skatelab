"use client"

import { useTranslations } from "@/i18n"
import { Button } from "@/components/ui/button"
import FocusLock from "react-focus-lock"

interface CookieBannerProps {
  onAccept: () => void
  onDecline: () => void
}

export default function CookieBanner({ onAccept, onDecline }: CookieBannerProps) {
  /** CookieBanner uses default export for dynamic import compatibility */
  const t = useTranslations("landing")

  return (
    <FocusLock returnFocus>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cookie-heading"
        className="fixed bottom-0 left-0 right-0 z-[70] border-t border-hairline bg-canvas-soft shadow-lg shadow-primary/5 pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto max-w-5xl px-6 py-4">
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 id="cookie-heading" className="sr-only">
                {t("cookieHeading")}
              </h2>
              <p className="sh-body-md text-ink-mute">
                {t("cookieText")}{" "}
                <a href="/cookies" className="text-link hover:underline">
                  Cookie Policy
                </a>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                onClick={onDecline}
                className="min-h-[44px] min-w-[120px] shrink-0"
              >
                {t("cookieDecline")}
              </Button>
              <Button onClick={onAccept} autoFocus className="min-h-[44px] min-w-[120px] shrink-0">
                {t("cookieAccept")}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </FocusLock>
  )
}
