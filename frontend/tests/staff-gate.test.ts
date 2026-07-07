import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// Module-level toggle so each test controls what cookies.get() returns.
// vi.mock factory is hoisted and cannot reference outer-scope let, so the
// factory reads from a closure variable assigned after the mock is wired.
let cookieValue: { value: string } | undefined = { value: "jwt-token" }

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (_name: string) => cookieValue,
  }),
}))

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT:${url}`)
  },
}))

const fetchMock = vi.fn()
global.fetch = fetchMock as unknown as typeof fetch

import { getStaffStatus, requireStaff } from "../src/lib/staff"

describe("staff gate", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    cookieValue = { value: "jwt-token" }
  })

  afterEach(() => {
    fetchMock.mockReset()
  })

  it("isStaff true when /v1/users/me returns is_staff=true", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ is_staff: true }),
    })
    const { isStaff } = await getStaffStatus()
    expect(isStaff).toBe(true)
  })

  it("isStaff false when /v1/users/me returns is_staff=false", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ is_staff: false }),
    })
    const { isStaff } = await getStaffStatus()
    expect(isStaff).toBe(false)
  })

  it("isStaff false when no sk_session cookie present", async () => {
    cookieValue = undefined
    const { isStaff } = await getStaffStatus()
    expect(isStaff).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("requireStaff redirects to /login?next=... when not staff", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ is_staff: false }),
    })
    await expect(requireStaff("/ru/internal/architecture")).rejects.toThrow(
      "REDIRECT:/login?next=" + encodeURIComponent("/ru/internal/architecture"),
    )
  })

  it("internal page source declares dynamic = 'force-dynamic' (build-hang bypass)", async () => {
    // ponytail: the page module top-level `loader()` invocation requires the
    // Fumadocs-generated `.source/server` entry, which re-imports MDX files
    // with a `?collection=docs` virtual suffix that only next-build resolves.
    // We can't import the module in vitest; the export contract is enforced
    // by reading the source instead. Bun's transpiler can't be used either
    // for the same reason.
    const { readFileSync } = await import("node:fs")
    const src = readFileSync("src/app/(docs)/[locale]/internal/[[...slug]]/page.tsx", "utf8")
    expect(src).toMatch(/export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/)
  })
})
