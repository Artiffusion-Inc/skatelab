import { describe, it, expect } from "vitest"

describe("robots disallow internal", () => {
  it("disallow rule exists", async () => {
    const mod = await import("../src/app/(docs)/[locale]/robots")
    const { rules } = mod.default()
    const disallows = (rules as any[]).flatMap((r: any) =>
      Array.isArray(r.disallow) ? r.disallow : [r.disallow].filter(Boolean),
    )
    expect(disallows).toContain("/internal/")
  })
})
