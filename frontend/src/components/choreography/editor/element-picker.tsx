"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "@/i18n"
import { useElementsRegistry } from "@/lib/api/choreography"
import type { TrackType } from "@/types/choreography"

interface ElementPickerProps {
  trackType: TrackType
  onSelect: (code: string) => void
  onClose: () => void
}

function typeMatches(trackType: TrackType, apiType: string): boolean {
  if (trackType === "jumps") return apiType === "jump"
  if (trackType === "spins") return apiType === "spin"
  return apiType === "step_sequence" || apiType === "choreo_sequence"
}

export function ElementPicker({ trackType, onSelect, onClose }: ElementPickerProps) {
  const [search, setSearch] = useState("")
  const t = useTranslations("choreography.timeline")
  const { data, isLoading } = useElementsRegistry()

  const items = useMemo(() => {
    if (!data) return []
    return data.elements
      .filter(el => typeMatches(trackType, el.type))
      .map(el => ({ code: el.code, name: el.name, bv: el.base_value }))
  }, [data, trackType])

  const filtered = useMemo(() => {
    if (!search) return items
    const q = search.toLowerCase()
    return items.filter(
      el => el.code.toLowerCase().includes(q) || el.name.toLowerCase().includes(q),
    )
  }, [search, items])

  return (
    <div
      role="dialog"
      aria-label="Pick element"
      className="w-64 rounded-lg border border-border bg-background p-2 shadow-lg"
      onClick={e => e.stopPropagation()}
      onKeyDown={e => {
        if (e.key === "Escape") onClose()
      }}
    >
      <label htmlFor="element-search" className="sr-only">
        {t("searchLabel")}
      </label>
      <input
        id="element-search"
        type="text"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder={t("search")}
        className="mb-2 w-full rounded-md border border-border bg-muted/30 px-2 py-1 text-sm outline-none focus:border-primary"
      />
      <div className="max-h-60 overflow-y-auto">
        {isLoading && (
          <p className="py-2 text-center text-xs text-muted-foreground">{t("loading")}</p>
        )}
        {!isLoading &&
          filtered.map(el => (
            <button
              key={el.code}
              type="button"
              className="flex w-full items-center justify-between rounded px-2 py-1 text-sm hover:bg-muted/50"
              onClick={() => {
                onSelect(el.code)
                onClose()
              }}
            >
              <span className="font-medium">{el.code}</span>
              <span className="text-xs text-muted-foreground">{el.bv.toFixed(1)}</span>
            </button>
          ))}
        {!isLoading && filtered.length === 0 && (
          <p className="py-2 text-center text-xs text-muted-foreground">{t("notFound")}</p>
        )}
      </div>
    </div>
  )
}
