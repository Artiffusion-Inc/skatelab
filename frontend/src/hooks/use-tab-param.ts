// frontend/src/hooks/use-tab-param.ts
"use client"

import { useSearchParams } from "next/navigation"
import { useCallback, useState } from "react"

const VALID_TABS = ["overview", "details", "analyzer", "export"] as const
type Tab = (typeof VALID_TABS)[number]

export function useTabParam(defaultTab: Tab = "overview") {
  const searchParams = useSearchParams()
  // #529: initialize localTab from the URL on first render so deep links
  // still work (?tab=details on first load). After mount, the URL is
  // informational only — the source of truth is localTab (which setTab
  // updates). window.history.replaceState does NOT notify useSearchParams
  // (only Next's router does), so reading urlTab after mount gives a
  // frozen stale snapshot that overrides the just-clicked localTab.
  const [localTab, setLocalTab] = useState<Tab>(() => {
    const urlTab = searchParams.get("tab") as Tab | null
    return urlTab && VALID_TABS.includes(urlTab) ? urlTab : defaultTab
  })

  // activeTab = localTab. The URL ?tab= is the initial value; the user's
  // subsequent clicks update localTab and the URL is kept in sync for
  // shareable links, but the URL is never read again as a source of
  // truth (it would race with setTab → ui desync).
  const activeTab = localTab

  const setTab = useCallback((tab: Tab) => {
    setLocalTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set("tab", tab)
    window.history.replaceState(null, "", url.toString())
  }, [])

  return { activeTab, setTab }
}
