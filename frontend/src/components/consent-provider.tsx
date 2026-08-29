"use client"

import { createContext, useCallback, useContext, useState, type ReactNode } from "react"
import { posthog } from "posthog-js"
import { posthogKey } from "@/lib/env"
import { useMountEffect } from "@/lib/useMountEffect"

export interface ConsentState {
  essential: boolean
  analytics: boolean
  recordings: boolean
}

interface ConsentContextValue extends ConsentState {
  setConsent: (state: ConsentState) => void
  hasConsented: (category: "analytics" | "recordings") => boolean
  showBanner: boolean
  dismissBanner: () => void
}

const STORAGE_KEY = "skatelab_consent"
const OLD_KEY = "consent_accepted"

const ConsentContext = createContext<ConsentContextValue | null>(null)

function readConsent(): ConsentState {
  if (typeof window === "undefined") {
    return { essential: true, analytics: false, recordings: false }
  }

  // Migration: old boolean consent → new 3-tier
  const old = localStorage.getItem(OLD_KEY)
  if (old !== null) {
    const migrated: ConsentState = {
      essential: true,
      analytics: old === "true",
      recordings: old === "true",
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated))
    localStorage.removeItem(OLD_KEY)
    return migrated
  }

  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored) {
    try {
      return JSON.parse(stored) as ConsentState
    } catch {
      // Corrupted — reset
    }
  }

  return { essential: true, analytics: false, recordings: false }
}

function writeConsent(state: ConsentState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  // Cookie for server-side consent detection
  const consentCookie = `skatelab_consent=analytics:${state.analytics},recordings:${state.recordings}; path=/; max-age=31536000; SameSite=Lax`
  // biome-ignore lint/suspicious/noDocumentCookie: intentional consent cookie for SSR detection
  document.cookie = consentCookie
}

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsentState] = useState<ConsentState>({
    essential: true,
    analytics: false,
    recordings: false,
  })
  const [showBanner, setShowBanner] = useState(true)
  const [initialized, setInitialized] = useState(false)

  useMountEffect(() => {
    const stored = readConsent()
    setConsentState(stored)
    setShowBanner(!localStorage.getItem(STORAGE_KEY))
    setInitialized(true)

    // Sync PostHog with stored consent on mount
    if (posthogKey && stored.analytics) {
      setTimeout(() => {
        posthog.opt_in_capturing()
        if (stored.recordings) {
          posthog.startSessionRecording()
        }
      }, 100)
    }
  })

  const setConsent = useCallback((state: ConsentState) => {
    setConsentState(state)
    writeConsent(state)
    setShowBanner(false)

    // Sync PostHog with consent state
    if (!posthogKey) return
    if (state.analytics) {
      posthog.opt_in_capturing()
    } else {
      posthog.opt_out_capturing()
    }
    if (state.recordings) {
      posthog.startSessionRecording()
    } else {
      posthog.stopSessionRecording()
    }
  }, [])

  const dismissBanner = useCallback(() => {
    setShowBanner(false)
  }, [])

  const hasConsented = useCallback(
    (category: "analytics" | "recordings") => consent[category],
    [consent],
  )

  if (!initialized) return null

  return (
    <ConsentContext.Provider
      value={{ ...consent, setConsent, hasConsented, showBanner, dismissBanner }}
    >
      {children}
    </ConsentContext.Provider>
  )
}

export function useConsent() {
  const ctx = useContext(ConsentContext)
  if (!ctx) throw new Error("useConsent must be used within ConsentProvider")
  return ctx
}
