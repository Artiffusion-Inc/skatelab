/**
 * Repro — resend-verification shows a SUCCESS toast on FAILURE, misleading the
 * user and hiding real errors (rate-limit, network, backend rejection).
 *
 * `ResendVerificationPage.handleSubmit` (src/app/(auth)/resend-verification/page.tsx:26-34):
 *
 *   try {
 *     await resendVerification(email)
 *     setSent(true)
 *     toast.success(t("resendSuccess"), { duration: 3000 })
 *   } catch {
 *     toast.success(t("resendSuccess"), { duration: 3000 })   // ← BUG: success on error
 *   } finally { setLoading(false) }
 *
 * The `catch` branch shows the SAME `toast.success("resendSuccess")` as the
 * happy path. So when `resendVerification` throws — e.g. HTTP 429 rate-limit
 * (`resend_ip` is capped at 3/hour on the backend, auth.py:386), a network
 * failure, or any backend rejection — the user sees "Письмо отправлено" ("Email
 * sent") and the `sent`-state UI ("Письмо отправлено! Если email
 * зарегистрирован..."). The user believes the verification email was sent when
 * it was not.
 *
 * There is a security rationale for NOT revealing whether an email exists
 * (anti-enumeration) — the backend deliberately returns a generic message. But
 * that rationale applies to the EXISTENCE of the account, NOT to transport /
 * rate-limit / network errors. Collapsing 429 (rate-limit) and network-down into
 * a success toast hides real, actionable failures and breaks user trust.
 *
 * Contrast: `login` (auth-provider.tsx:68) lets errors propagate / surfaces them
 * rather than swallowing as success. The resend page diverges.
 *
 * Repro: mock `resendVerification` to throw (simulating backend 429 / network),
 * mock `sonner` toast, render the page, submit a valid email, and assert that
 * `toast.success` was NOT called. RED now: it IS called (the catch branch fires
 * success). After the fix (catch shows `toast.error(t("resendFailed"))` or a
 * generic non-success message) → `toast.success` is not called on error.
 */

import { describe, expect, it, beforeEach, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"

// Mock resendVerification to throw (backend 429 / network failure).
const resendVerificationMock = vi.fn(
  async (_email: string): Promise<{ message: string }> => {
    throw new Error("HTTP 429")
  },
)
vi.mock("@/lib/auth", () => ({
  resendVerification: (email: string) => resendVerificationMock(email),
}))

// Capture toast.success / toast.error calls.
const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
  Toaster: () => null,
}))

import ResendVerificationPage from "@/app/(auth)/resend-verification/page"

function renderPage() {
  return render(<ResendVerificationPage />)
}

describe("resend-verification success-toast-on-failure (repro)", () => {
  beforeEach(() => {
    resendVerificationMock.mockClear()
    toastSuccess.mockClear()
    toastError.mockClear()
  })

  it("does NOT show a success toast when resendVerification fails", async () => {
    renderPage()

    const input = screen.getByLabelText(/email/i)
    fireEvent.change(input, { target: { value: "user@example.com" } })
    fireEvent.click(screen.getByRole("button", { name: /resend|Отправить|send/i }))

    // resendVerification was called and threw.
    await waitFor(() => expect(resendVerificationMock).toHaveBeenCalledTimes(1))

    // CONTRACT: a failure must NOT surface a success toast. RED now: the catch
    // branch calls toast.success("resendSuccess") — the user sees "Письмо
    // отправлено" even though the backend rejected/rate-limited the request.
    expect(toastSuccess).not.toHaveBeenCalled()
  })
})