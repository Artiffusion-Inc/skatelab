// frontend/src/hooks/use-tab-param.ts
"use client"

import { useSearchParams } from "next/navigation"
import { useCallback, useState } from "react"

const VALID_TABS = ["overview", "details", "export"] as const
type Tab = (typeof VALID_TABS)[number]

export function useTabParam(defaultTab: Tab = "overview") {
  const searchParams = useSearchParams()
  const [localTab, setLocalTab] = useState<Tab>(defaultTab)

  const urlTab = searchParams.get("tab") as Tab | null
  const activeTab = urlTab && VALID_TABS.includes(urlTab) ? urlTab : localTab

  const setTab = useCallback((tab: Tab) => {
    setLocalTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set("tab", tab)
    window.history.replaceState(null, "", url.toString())
  }, [])

  return { activeTab, setTab }
}
