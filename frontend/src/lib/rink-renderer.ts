interface RinkElement {
  code: string
  position: { x: number; y: number } | null
  timestamp?: number
  is_jump_pass?: boolean
}

const RINK_W = 30
const RINK_H = 61
const PAD = 0.5

function elementColor(code: string): string {
  if (code.includes("Sp")) return "#7c3aed"
  if (code.includes("StSq")) return "#16a34a"
  if (code.includes("ChSq")) return "#2563eb"
  return "#ea580c"
}

function _elementLabel(code: string): string {
  if (code.includes("Sp")) return "Вращение"
  if (code.includes("StSq")) return "Шаговая"
  if (code.includes("ChSq")) return "Хорео"
  return "Прыжок"
}

// #480: el.code is interpolated raw into <text> — an unescaped code breaks out
// of the SVG node (same unescaped-interpolation class as backend #464, latent
// here: renderRink has no live consumer but is an exported public-API footgun).
function _escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;")
}

// #480: clamp element coords to the rink viewBox so out-of-bounds positions do
// not land as raw negative/huge values in cx/cy/x/y attributes.
function _clampCoord(x: number, y: number): [number, number] {
  return [Math.max(0, Math.min(RINK_W, x)), Math.max(0, Math.min(RINK_H, y))]
}

function elementMarker(el: RinkElement, x: number, y: number): string {
  const color = elementColor(el.code)

  if (el.code.includes("Sp")) {
    return `<circle cx="${x}" cy="${y}" r="1.3" fill="${color}" opacity="0.25" stroke="${color}" stroke-width="0.15"/>`
  }
  if (el.code.includes("StSq")) {
    return `<rect x="${x - 1.2}" y="${y - 0.5}" width="2.4" height="1" fill="none" stroke="${color}" stroke-width="0.15" stroke-dasharray="0.4,0.2" rx="0.2"/>`
  }
  if (el.code.includes("ChSq")) {
    return `<polygon points="${x},${y - 0.9} ${x + 0.9},${y} ${x},${y + 0.9} ${x - 0.9},${y}" fill="${color}" opacity="0.2" stroke="${color}" stroke-width="0.15"/>`
  }
  // Jumps — filled circle
  return `<circle cx="${x}" cy="${y}" r="0.7" fill="${color}" opacity="0.85"/>`
}

function _faceOffCircles(): string[] {
  const parts: string[] = []
  const cx0 = RINK_W / 2
  const cy0 = RINK_H / 2
  const positions = [
    [cx0 - 6, cy0 - 11],
    [cx0 + 6, cy0 - 11],
    [cx0 - 6, cy0 + 11],
    [cx0 + 6, cy0 + 11],
  ]
  for (const [cx, cy] of positions) {
    parts.push(
      `<circle cx="${cx}" cy="${cy}" r="3" fill="none" stroke="#dc2626" stroke-width="0.08"/>`,
    )
  }
  return parts
}

function _faceOffDots(): string[] {
  const parts: string[] = []
  const cx0 = RINK_W / 2
  const cy0 = RINK_H / 2
  const positions = [
    [cx0, cy0],
    [cx0 - 6, cy0 - 11],
    [cx0 + 6, cy0 - 11],
    [cx0 - 6, cy0 + 11],
    [cx0 + 6, cy0 + 11],
  ]
  for (const [cx, cy] of positions) {
    parts.push(`<circle cx="${cx}" cy="${cy}" r="0.15" fill="#dc2626"/>`)
  }
  return parts
}

function _cornerCreases(): string[] {
  const parts: string[] = []
  const r = 1.8
  const configs = [
    { x: 0, y: 0, x1: r, y1: 0, x2: 0, y2: r },
    { x: RINK_W, y: 0, x1: RINK_W - r, y1: 0, x2: RINK_W, y2: r },
    { x: 0, y: RINK_H, x1: r, y1: RINK_H, x2: 0, y2: RINK_H - r },
    { x: RINK_W, y: RINK_H, x1: RINK_W - r, y1: RINK_H, x2: RINK_W, y2: RINK_H - r },
  ]
  for (const c of configs) {
    parts.push(
      `<path d="M ${c.x1} ${c.y1} A ${r} ${r} 0 0 1 ${c.x2} ${c.y2}" fill="none" stroke="#dc2626" stroke-width="0.08"/>`,
    )
  }
  return parts
}

export function renderRink(elements: RinkElement[], options?: { width?: number }): string {
  const maxW = options?.width ?? 1200

  const parts: string[] = []

  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 ${RINK_W} ${RINK_H}" style="max-width:${maxW}px">`,
  )

  // Ice surface
  parts.push(`<rect x="0" y="0" width="${RINK_W}" height="${RINK_H}" fill="#e8f0fe"/>`)

  // Boundary
  parts.push(
    `<rect x="0" y="0" width="${RINK_W}" height="${RINK_H}" rx="7.5" fill="none" stroke="#dc2626" stroke-width="0.15"/>`,
  )

  // Centre line (horizontal at mid-height)
  parts.push(
    `<line x1="0" y1="${RINK_H / 2}" x2="${RINK_W}" y2="${RINK_H / 2}" stroke="#dc2626" stroke-width="0.12"/>`,
  )

  // Blue lines
  parts.push(`<line x1="0" y1="8.5" x2="${RINK_W}" y2="8.5" stroke="#2563eb" stroke-width="0.1"/>`)
  parts.push(
    `<line x1="0" y1="52.5" x2="${RINK_W}" y2="52.5" stroke="#2563eb" stroke-width="0.1"/>`,
  )

  // End lines
  parts.push(`<line x1="0" y1="4" x2="${RINK_W}" y2="4" stroke="#dc2626" stroke-width="0.1"/>`)
  parts.push(`<line x1="0" y1="57" x2="${RINK_W}" y2="57" stroke="#dc2626" stroke-width="0.1"/>`)

  // Centre circle + dot
  parts.push(
    `<circle cx="${RINK_W / 2}" cy="${RINK_H / 2}" r="1.5" fill="none" stroke="#dc2626" stroke-width="0.1"/>`,
  )
  parts.push(`<circle cx="${RINK_W / 2}" cy="${RINK_H / 2}" r="0.12" fill="#dc2626"/>`)

  // Face-off circles and dots
  parts.push(..._faceOffCircles())
  parts.push(..._faceOffDots())

  // Corner creases
  parts.push(..._cornerCreases())

  // Flow lines: connect elements in chronological order (by timestamp)
  const sorted = elements
    .filter(el => el.position)
    .sort((a, b) => (a.timestamp ?? 0) - (b.timestamp ?? 0))

  for (let i = 0; i < sorted.length - 1; i++) {
    const from = sorted[i].position
    const to = sorted[i + 1].position
    if (!from || !to) continue
    const [fx, fy] = _clampCoord(from.x, from.y)
    const [tx, ty] = _clampCoord(to.x, to.y)
    const dx = tx - fx
    const dy = ty - fy
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < 2) continue

    parts.push(
      `<line x1="${fx}" y1="${fy}" x2="${tx}" y2="${ty}" stroke="#94a3b8" stroke-width="0.08" stroke-dasharray="0.6,0.4" opacity="0.5"/>`,
    )
    const mx = (fx + tx) / 2
    const my = (fy + ty) / 2
    const angle = Math.atan2(dy, dx)
    const arrowLen = 0.6
    const ax1 = mx - arrowLen * Math.cos(angle - 0.5)
    const ay1 = my - arrowLen * Math.sin(angle - 0.5)
    const ax2 = mx - arrowLen * Math.cos(angle + 0.5)
    const ay2 = my - arrowLen * Math.sin(angle + 0.5)
    parts.push(
      `<polyline points="${ax1},${ay1} ${mx},${my} ${ax2},${ay2}" fill="none" stroke="#94a3b8" stroke-width="0.08" opacity="0.5"/>`,
    )
  }

  // Elements with labels
  for (let i = 0; i < sorted.length; i++) {
    const el = sorted[i]
    const pos = el.position
    if (!pos) continue
    const [x, y] = _clampCoord(pos.x, pos.y)
    const color = elementColor(el.code)
    const num = i + 1

    parts.push(elementMarker(el, x, y))

    // Number badge
    parts.push(
      `<circle cx="${x + 1.2}" cy="${y - 1.0}" r="0.7" fill="white" stroke="${color}" stroke-width="0.12"/>`,
    )
    parts.push(
      `<text x="${x + 1.2}" y="${y - 0.65}" text-anchor="middle" font-size="0.85" fill="${color}" font-weight="bold">${num}</text>`,
    )

    // Element code below marker (escaped — #480, #464-class SVG injection)
    parts.push(
      `<text x="${x}" y="${y + 1.8}" text-anchor="middle" font-size="0.9" fill="#334155" font-weight="600">${_escapeXml(el.code)}</text>`,
    )
  }

  // Legend
  const ly = RINK_H - 2
  const legendItems = [
    { code: "3Lz", label: "Прыжок" },
    { code: "CSp4", label: "Вращение" },
    { code: "StSq4", label: "Шаговая" },
    { code: "ChSq1", label: "Хорео" },
  ]
  let lx = PAD + 1
  for (const item of legendItems) {
    const _color = elementColor(item.code)
    parts.push(elementMarker({ code: item.code } as RinkElement, lx + 0.4, ly))
    parts.push(
      `<text x="${lx + 1.6}" y="${ly + 0.35}" font-size="0.7" fill="#64748b">${item.label}</text>`,
    )
    lx += 6
  }

  parts.push("</svg>")
  return parts.join("\n")
}
