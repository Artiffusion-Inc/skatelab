"use client"

import { posthog } from "posthog-js"
import { posthogKey, posthogHost } from "@/lib/env"

export function isPostHogAvailable(): boolean {
  return !!posthogKey
}

export function identifyUser(userId: string, properties?: Record<string, unknown>) {
  if (!isPostHogAvailable()) return
  posthog.identify(userId, properties)
}

export function resetIdentity() {
  if (!isPostHogAvailable()) return
  posthog.reset()
}

export function captureEvent(event: string, properties?: Record<string, unknown>) {
  if (!isPostHogAvailable()) return
  posthog.capture(event, properties)
}