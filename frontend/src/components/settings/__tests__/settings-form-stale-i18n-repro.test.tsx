/**
 * Repro — SettingsForm language change is a no-op: handleSubmit PATCHes the
 * DB (updateSettings) but never calls setLocale (NEXT_LOCALE cookie) nor
 * router.refresh(), so the UI stays in the old language — even reload won't
 * help (the cookie was never written).
 *
 * `SettingsForm.handleSubmit` (src/components/settings/settings-form.tsx:22-33):
 *
 *   async function handleSubmit(e) {
 *     e.preventDefault()
 *     setSaving(true)
 *     try {
 *       await updateSettings({ language, timezone, theme })
 *       toast.success(t("saved"))
 *     } catch { toast.error(t("saveError")) }
 *     finally { setSaving(false) }
 *   }
 *
 * No `setLocale(language)`, no `router.refresh()`, no `setUser`/query
 * invalidation. Compare `frontend/src/i18n/actions.ts:9-17` — the `setLocale`
 * server action writes the NEXT_LOCALE cookie and is NEVER called from
 * settings-form. `app/layout.tsx` resolves locale/messages server-side via
 * `getLocale()` (reads NEXT_LOCALE cookie), baked into NextIntlClientProvider
 * at SSR. Without setLocale + refresh the UI stays in the old language; the
 * cookie is never written so even a reload stays old; useAuth().user.language
 * stays stale (no setUser).
 *
 * Repro: mock updateSettings to resolve, mock setLocale + useRouter.refresh,
 * render SettingsForm, change the language <select> to "en", submit, assert
 * that after a successful save the UI switches — setLocale("en") OR
 * router.refresh() fires. RED now: neither fires (only updateSettings + toast).
 * After the fix (setLocale(language) + router.refresh() after save) → GREEN.
 */

import { describe, expect, it, beforeEach, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"

// Mock updateSettings (DB PATCH) to resolve successfully.
const updateSettingsMock = vi.fn(async (_data: unknown): Promise<unknown> => ({ ok: true }))
vi.mock("@/lib/auth", () => ({
  updateSettings: (data: unknown) => updateSettingsMock(data),
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

// Mock @/i18n — useTranslations returns a fn returning the key (track keys).
vi.mock("@/i18n", () => ({
  useTranslations: () => (key: string) => key,
}))

// Provide an authenticated user via the auth context (language ru → change to en).
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

// Mock next/navigation useRouter — capture refresh/push.
const refreshMock = vi.fn()
const pushMock = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock, push: pushMock }),
}))

// Mock @/i18n/actions — capture setLocale calls. RED: never called by
// settings-form.
const setLocaleMock = vi.fn(async (_locale: unknown): Promise<void> => {})
vi.mock("@/i18n/actions", () => ({
  setLocale: (locale: unknown) => setLocaleMock(locale),
}))

import { SettingsForm } from "../settings-form"

describe("SettingsForm language change applies setLocale + refresh (repro)", () => {
  beforeEach(() => {
    updateSettingsMock.mockClear()
    toastSuccess.mockClear()
    toastError.mockClear()
    refreshMock.mockClear()
    pushMock.mockClear()
    setLocaleMock.mockClear()
  })

  it("calls setLocale(language) or router.refresh() after a successful language save (not just DB PATCH)", async () => {
    render(<SettingsForm />)

    // The language <select> has label text from t("language") → "language".
    const langSelect = screen.getByLabelText(/language/i) as HTMLSelectElement
    expect(langSelect).toBeTruthy()
    // Change to English.
    fireEvent.change(langSelect, { target: { value: "en" } })

    // Submit the form — the save button shows t("save") → "save".
    const saveButton = screen.getByRole("button", { name: /save/i })
    fireEvent.click(saveButton)

    // The DB PATCH happened (this is the only thing the current code does).
    await waitFor(() =>
      expect(updateSettingsMock).toHaveBeenCalledWith({
        language: "en",
        timezone: "Europe/Moscow",
        theme: "dark",
      }),
    )

    // CONTRACT: after a successful language save, the UI must switch —
    // setLocale("en") (writes NEXT_LOCALE cookie) OR router.refresh()
    // (re-renders with new SSR locale). RED now: neither fires.
    const applied = setLocaleMock.mock.calls.length > 0 || refreshMock.mock.calls.length > 0
    expect(
      applied,
      "BUG (stale-i18n / missing-side-effect-after-mutation): SettingsForm." +
        "handleSubmit (settings-form.tsx:22-33) calls updateSettings (DB " +
        "PATCH /users/me/settings) + toast.success + setSaving(false) but " +
        "NEVER calls setLocale (i18n/actions.ts:9-17 server action writes " +
        "NEXT_LOCALE cookie) NOR router.refresh() NOR setUser/query " +
        "invalidation. app/layout.tsx resolves locale/messages server-side " +
        "via getLocale() (reads NEXT_LOCALE cookie), baked into " +
        "NextIntlClientProvider at SSR — without setLocale+refresh the UI " +
        "stays in the old language; the cookie is never written so even a " +
        "reload stays old; useAuth().user.language stays stale. Every user " +
        "changing language via Settings experiences a no-op UI; persisted " +
        "DB preference diverges from displayed language. Fix: after " +
        "successful updateSettings, call setLocale(language) + " +
        "router.refresh() to apply.",
    ).toBe(true)

    // Pin which side-effect fired (for the failure message clarity).
    if (setLocaleMock.mock.calls.length === 0 && refreshMock.mock.calls.length === 0) {
      throw new Error(
        "RED: setLocale never called AND router.refresh never called — only " +
          "updateSettings (DB PATCH) fired. Language change is a no-op in the UI.",
      )
    }
  })
})
