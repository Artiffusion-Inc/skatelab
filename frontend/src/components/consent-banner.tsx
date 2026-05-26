"use client"

import { useState } from "react"
import { useTranslations } from "@/i18n"
import { useConsent } from "@/components/consent-provider"
import { Button } from "@/components/ui/button"
import FocusLock from "react-focus-lock"

export function ConsentBanner() {
  const t = useTranslations("landing")
  const { setConsent, showBanner } = useConsent()
  const [showCustomize, setShowCustomize] = useState(false)
  const [analytics, setAnalytics] = useState(false)
  const [recordings, setRecordings] = useState(false)

  if (!showBanner) return null

  function handleAcceptAll() {
    setConsent({ essential: true, analytics: true, recordings: true })
  }

  function handleAcceptSelected() {
    setConsent({ essential: true, analytics, recordings })
  }

  function handleDecline() {
    setConsent({ essential: true, analytics: false, recordings: false })
  }

  return (
    <FocusLock returnFocus>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-heading"
        className="fixed bottom-0 left-0 right-0 z-[70] border-t border-hairline bg-canvas-soft pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto max-w-5xl px-6 py-4">
          {!showCustomize ? (
            <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 id="consent-heading" className="sr-only">
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
                  onClick={() => setShowCustomize(true)}
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  Customize
                </Button>
                <Button
                  onClick={handleDecline}
                  variant="ghost"
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  {t("cookieDecline")}
                </Button>
                <Button
                  onClick={handleAcceptAll}
                  autoFocus
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  {t("cookieAccept")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <h2 id="consent-heading" className="sh-heading-lg text-ink">
                Cookie Preferences
              </h2>
              <div className="space-y-3">
                <label className="flex items-center gap-3">
                  <input type="checkbox" checked disabled className="accent-primary" />
                  <span className="sh-body-md text-ink">Essential (required)</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={analytics}
                    onChange={e => setAnalytics(e.target.checked)}
                    className="accent-primary"
                  />
                  <span className="sh-body-md text-ink">Analytics (pageviews, events)</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={recordings}
                    onChange={e => setRecordings(e.target.checked)}
                    className="accent-primary"
                  />
                  <span className="sh-body-md text-ink">
                    Session Recordings (heatmaps, replays)
                  </span>
                </label>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => setShowCustomize(false)}
                  className="min-h-[44px] shrink-0"
                >
                  Back
                </Button>
                <Button
                  onClick={handleAcceptSelected}
                  className="min-h-[44px] min-w-[120px] shrink-0"
                >
                  Save Preferences
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </FocusLock>
  )
}
