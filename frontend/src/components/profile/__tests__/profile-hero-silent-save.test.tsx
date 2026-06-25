/**
 * Repro — ProfileHero `saveBody` silently swallows height/weight save failures
 * (no error feedback), unlike the name/bio `save` which shows an error toast.
 *
 * `ProfileHero.saveBody` (src/components/profile/profile-hero.tsx:31-44):
 *
 *   const saveBody = async () => {
 *     if (saving) return
 *     setSaving(true)
 *     try {
 *       await updateProfile({ height_cm: ..., weight_kg: ... })
 *     } catch {
 *       // silent fail        ← BUG: no toast, no surface, user thinks it saved
 *     } finally { setSaving(false) }
 *   }
 *
 * The height/weight inputs fire `saveBody` on `onBlur` (profile-hero.tsx:162, 173).
 * If `updateProfile` fails (token expired → 401, network down, 5xx), the user
 * sees the `saving` indicator flash and vanish with NO error. The user believes
 * their height/weight change was saved when it was not.
 *
 * Contrast — the SAME component's `save()` for display_name/bio
 * (profile-hero.tsx:51-63):
 *
 *   try { await updateProfile({...}); toast.success(t("updateSuccess")) ... }
 *   catch { toast.error(t("updateError")) }
 *
 * name/bio save surfaces a `toast.error` on failure; height/weight save is
 * silent. Inconsistent recovery story within one component.
 *
 * Repro: mock `updateProfile` to throw (simulating 401/network), mock `sonner`
 * toast, render ProfileHero with an authenticated user, change the height
 * input and blur it (triggers saveBody), assert that `toast.error` (or any
 * error surfacing) was called. RED now: no toast is called at all (silent
 * fail). After the fix (catch shows `toast.error(t("updateError"))`) → GREEN.
 */

import { describe, expect, it, beforeEach, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"

// Mock updateProfile to throw (401 / network failure).
const updateProfileMock = vi.fn(async (_data: unknown): Promise<unknown> => {
  throw new Error("HTTP 401")
})
vi.mock("@/lib/auth", () => ({
  updateProfile: (data: unknown) => updateProfileMock(data),
}))

// Capture toast calls.
const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock("sonner", () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
  Toaster: () => null,
}))

// Mock @/i18n (already done globally in setup, but pin per-file for isolation).
vi.mock("@/i18n", () => ({
  useTranslations: () => (key: string) => key,
}))

// Provide an authenticated user via the auth context.
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      email: "u@example.com",
      display_name: "U",
      bio: null,
      height_cm: 180,
      weight_kg: 75,
      language: "ru",
      timezone: "Europe/Moscow",
      theme: "dark",
      onboarding_role: null,
      is_active: true,
      is_verified: true,
      created_at: "2026-01-01T00:00:00Z",
    },
  }),
}))

import { ProfileHero } from "@/components/profile/profile-hero"

describe("ProfileHero height/weight save silent-fail (repro)", () => {
  beforeEach(() => {
    updateProfileMock.mockClear()
    toastSuccess.mockClear()
    toastError.mockClear()
  })

  it("surfaces an error when height save fails (not silent)", async () => {
    render(<ProfileHero />)

    // Find the height input (it has min=50 max=250 from profile-hero.tsx:164-165).
    const heightInput = document.querySelector('input[type="number"][min="50"]') as HTMLInputElement
    expect(heightInput).toBeTruthy()

    fireEvent.change(heightInput, { target: { value: "185" } })
    fireEvent.blur(heightInput) // triggers saveBody()

    await waitFor(() => expect(updateProfileMock).toHaveBeenCalled())

    // CONTRACT: a failed save must surface an error (toast.error), matching the
    // name/bio save() path. RED now: saveBody catches and does nothing → no
    // toast at all → user thinks "185" was saved when updateProfile threw.
    expect(toastError).toHaveBeenCalled()
  })
})
