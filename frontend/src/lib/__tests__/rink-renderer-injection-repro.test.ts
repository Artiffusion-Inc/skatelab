/**
 * RED repro: renderRink interpolates el.code + position raw into SVG markup.
 *
 * Root cause (rink-renderer.ts):
 *  - el.code interpolated raw into <text> (line ~191)
 *  - position.x / position.y interpolated raw into cx/cy/x/y attributes
 *    (lines ~30, 154, 183, 186) and into <line x1/y1/x2/y2> (line ~154)
 *  - No XML escape on code, no coord clamp on position.
 *  - code = '3Lz"><script>alert(1)</script>' → literal <script> in SVG.
 *  - negative/huge coords → out-of-bounds raw values in attributes.
 *
 * LATENT: renderRink has NO production consumer (RinkDiagram component builds its own
 * React SVG, does not import renderRink). Exported public API footgun. Element codes
 * server-constrained to ISU codes. Same unescaped-interpolation class as backend #464
 * (which WAS live). File with "latent" note.
 */
import { describe, expect, it } from "vitest"
import { renderRink } from "../rink-renderer"

describe("renderRink SVG injection (latent, #464-class)", () => {
  it("rejects SVG injection in code (no raw <script>)", () => {
    const svg = renderRink([{ code: '3Lz"><script>alert(1)</script>', position: { x: 15, y: 30 } }])
    // RED: svg contains literal "<script>" because el.code is interpolated raw.
    expect(svg).not.toContain("<script>")
  })

  it("clamps out-of-bounds position (no raw negative coords)", () => {
    const svg = renderRink([{ code: "3Lz", position: { x: -100, y: -200 } }])
    // RED: raw negative coords land in cx/cy/x/y attributes unclamped.
    expect(svg).not.toContain('x="-100"')
    expect(svg).not.toContain('y="-200"')
  })
})
