"use client"

import { useFeatureFlag as usePostHogFeatureFlag } from "@posthog/next"
import type { FlagKey } from "@/lib/flags"

interface FlagResult {
  enabled: boolean
  variant?: string
}

export function useFeatureFlagSafe(key: FlagKey): FlagResult {
  const flag = usePostHogFeatureFlag(key)

  if (!flag) return { enabled: false }
  if (typeof flag === "boolean") return { enabled: flag }
  if (typeof flag === "string") {
    if (flag.startsWith("holdout-")) return { enabled: false }
    return { enabled: true, variant: flag }
  }
  return { enabled: flag.enabled ?? false, variant: flag.variant }
}