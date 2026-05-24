"use client"

import { useRouter } from "next/navigation"
import { OnboardingFlow } from "@/components/onboarding"
import type { OnboardingData } from "@/components/onboarding"
import { updateOnboardingRole } from "@/lib/auth"
import { captureEvent } from "@/lib/posthog"

export default function OnboardingPage() {
  const router = useRouter()

  const handleComplete = async (data: OnboardingData) => {
    // Store onboarding completion locally
    localStorage.setItem("onboarding_completed", "true")
    localStorage.setItem("onboarding_role", data.role)
    localStorage.setItem("onboarding_source", data.source)
    captureEvent("onboarding_step", {
      step: data.skipped ? "skipped" : "completed",
      role: data.role,
    })
    if (data.skipped) {
      localStorage.setItem("onboarding_skipped", "true")
    }

    // Sync role to backend (best-effort)
    try {
      await updateOnboardingRole(data.role)
    } catch {
      // localStorage acts as fallback
    }

    // Redirect based on role
    if (data.role === "coach") {
      router.push("/dashboard")
    } else {
      router.push("/feed")
    }
  }

  return <OnboardingFlow onComplete={handleComplete} />
}
