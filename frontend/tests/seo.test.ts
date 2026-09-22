import { describe, it, expect } from "vitest"

describe("robots disallow internal", () => {
  it("disallow rule exists", async () => {
    const mod = await import("../src/app/(docs)/[locale]/robots")
    const { rules } = mod.default()
    const disallows = (rules as Array<{ disallow?: string | string[] }>).flatMap(({ disallow }) =>
      Array.isArray(disallow) ? disallow : [disallow].filter(Boolean),
    )
    expect(disallows).toContain("/internal/")
  })
})
