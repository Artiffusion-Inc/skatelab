// src/hooks/use-metric-registry.ts
import { useQuery } from "@tanstack/react-query"
import * as z from "zod"
import { apiFetch } from "@/lib/api-client"
import { useLocale } from "@/i18n"

// ---------------------------------------------------------------------------
// Metric registry (static metric definitions)
// ---------------------------------------------------------------------------

const RegistrySchema = z.record(
  z.string(),
  z.object({
    name: z.string(),
    label_ru: z.string(),
    unit: z.string(),
    format: z.string(),
    direction: z.enum(["higher", "lower"]),
    element_types: z.array(z.string()),
    ideal_range: z.tuple([z.number(), z.number()]),
  }),
)

export type MetricRegistry = z.infer<typeof RegistrySchema>

export function useMetricRegistry() {
  return useQuery({
    queryKey: ["metric-registry"],
    queryFn: () => apiFetch("/metrics/registry", RegistrySchema),
    staleTime: Infinity,
  })
}

// ---------------------------------------------------------------------------
// ISU element registry (canonical codes + localized names)
// ---------------------------------------------------------------------------

const ElementSchema = z.object({
  code: z.string(),
  name_ru: z.string(),
  name_en: z.string(),
  type: z.string(),
  family: z.string(),
  rotations: z.number(),
  base_value: z.number(),
})

const ElementRegistrySchema = z.object({
  registry_version: z.number(),
  elements: z.array(ElementSchema),
})

export type ElementEntry = z.infer<typeof ElementSchema>
export type ElementRegistry = z.infer<typeof ElementRegistrySchema>

export function useElementRegistry() {
  return useQuery({
    queryKey: ["element-registry"],
    queryFn: () => apiFetch("/metrics/elements", ElementRegistrySchema),
    staleTime: Infinity,
  })
}

/**
 * Map of ISU code → element entry, built from the registry response.
 * Returns `undefined` while the registry is loading or if the code is unknown.
 */
export function useElementMap(): Record<string, ElementEntry> | undefined {
  const { data } = useElementRegistry()
  if (!data) return undefined
  const map: Record<string, ElementEntry> = {}
  for (const e of data.elements) map[e.code] = e
  return map
}

/**
 * Returns a function that renders the label for an ISU element code:
 * "<code> — <localized name>".
 *
 * Picks `name_ru` for the Russian locale, `name_en` otherwise. Falls back to the
 * raw code when the code is not in the registry (e.g. registry still loading).
 *
 * Note: the returned function is rebuilt each render (the underlying
 * `useElementMap` rebuilds its map each render). It is not memoized — fine for
 * label rendering, but avoid depending on referential equality.
 *
 * Usage: `const label = useElementLabel()` then `label("3A")` per item.
 */
export function useElementLabel(): (code: string) => string {
  const map = useElementMap()
  const locale = useLocale()
  return (code: string): string => {
    const entry = map?.[code]
    if (!entry) return code
    const name = locale === "ru" ? entry.name_ru : entry.name_en
    return `${code} — ${name}`
  }
}
