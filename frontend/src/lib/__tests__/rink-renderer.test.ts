import { describe, expect, it } from "vitest"
import { renderRink } from "../rink-renderer"

describe("renderRink", () => {
  it("returns SVG string with rink outline", () => {
    const svg = renderRink([])
    expect(svg).toContain("<svg")
    expect(svg).toContain("</svg>")
    expect(svg).toContain("max-width:1200")
    expect(svg).toContain('viewBox="0 0 30 61"')
  })

  for (const { note, code, color, position } of [
    { note: "jump elements", code: "3Lz", color: "#ea580c", position: { x: 30, y: 15 } },
    { note: "spin elements", code: "CSp4", color: "#7c3aed", position: { x: 20, y: 10 } },
    { note: "step sequences", code: "StSq4", color: "#16a34a", position: { x: 40, y: 10 } },
    { note: "choreo sequences", code: "ChSq1", color: "#2563eb", position: { x: 15, y: 20 } },
  ]) {
    it(`renders ${note}`, () => {
      const svg = renderRink([{ code, position }])
      expect(svg).toContain(code)
      expect(svg).toContain(color)
    })
  }

  it("draws connecting paths between elements", () => {
    const svg = renderRink([
      { code: "3Lz", position: { x: 10, y: 20 } },
      { code: "3F", position: { x: 20, y: 40 } },
    ])
    expect(svg).toContain('x1="10"')
    expect(svg).toContain('x2="20"')
  })

  it("skips elements without position", () => {
    const svg = renderRink([{ code: "3Lz", position: null }])
    expect(svg).not.toContain("3Lz")
  })

  it("supports custom width", () => {
    const svg = renderRink([], { width: 600 })
    expect(svg).toContain("max-width:600")
  })
})
