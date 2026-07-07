import { describe, it, expect } from "vitest"

describe("source config", () => {
  it("imports without error and exports docs + blog collections", async () => {
    const mod = await import("../source.config")
    expect(mod.docs).toBeDefined()
    expect(mod.blog).toBeDefined()
  })
})