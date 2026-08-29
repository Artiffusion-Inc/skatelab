/**
 * RED→GREEN repro tests for issues #829–#831 (frontend upload/stream audit).
 *
 * #829 useProcessStream unknown-status / _timeout payload never closes stream
 * #830 DropZone MAX_SIZE gate checks pre-compression size
 * #831 Progress value 0..1 from backend fed to component expecting 0..100
 *
 * Source-asserting (read source + assert the fix is present) for the
 * pure-source bugs (#830, #831) and behavioral for the SSE lifecycle bug (#829).
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { readFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { useProcessStream } from "../use-process-stream"

const HOOKS_DIR = dirname(new URL(import.meta.url).pathname)
const SRC_DIR = join(HOOKS_DIR, "..", "..")
const COMPONENTS_DIR = join(SRC_DIR, "components")

function readSrc(rel: string): string {
  return readFileSync(join(SRC_DIR, rel), "utf-8")
}

// ---------------------------------------------------------------------------
// EventSource mock (mirrors the no-retry repro test's harness)
// ---------------------------------------------------------------------------

let instances: MockEventSource[] = []

class MockEventSource {
  url: string
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  readyState = 0
  closed = false

  constructor(url: string) {
    this.url = url
    instances.push(this)
  }
  close() {
    this.closed = true
    this.readyState = 2
  }
  fireOpen() {
    this.readyState = 1
    this.onopen?.(new Event("open"))
  }
  fireMessage(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }
}

beforeEach(() => {
  instances = []
  vi.stubGlobal("EventSource", MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// #829: unknown-status / _timeout payloads must close the stream
// ---------------------------------------------------------------------------

describe("#829 useProcessStream unknown/timeout terminal payloads", () => {
  it("closes the EventSource and surfaces failed on {status:unknown}", async () => {
    const { result, unmount } = renderHook(() => useProcessStream("task-unknown"))

    await waitFor(() => expect(instances.length).toBeGreaterThanOrEqual(1))
    const es = instances[0]!
    es.fireOpen()
    expect(es.closed).toBe(false)

    act(() => {
      // Backend process.py:131 payload for an unknown/unowned task.
      es.fireMessage(JSON.stringify({ status: "unknown" }))
    })

    await waitFor(() => expect(es.closed).toBe(true))
    expect(
      result.current.state?.status,
      `BUG #829: {"status":"unknown"} must surface as a terminal/failed status ` +
        `so ProcessingBanner stops rendering "analyzing" for a dead task. ` +
        `Got status=${result.current.state?.status}.`,
    ).toBe("failed")
    expect(result.current.isConnected).toBe(false)

    unmount()
  })

  it("closes the EventSource on a _timeout-tagged payload", async () => {
    const { result, unmount } = renderHook(() => useProcessStream("task-timeout"))

    await waitFor(() => expect(instances.length).toBeGreaterThanOrEqual(1))
    const es = instances[0]!
    es.fireOpen()

    act(() => {
      // Backend process.py:148 payload after the 60s inactivity timeout.
      es.fireMessage(JSON.stringify({ status: "running", progress: 0.7, _timeout: true }))
    })

    await waitFor(() => expect(es.closed).toBe(true))
    expect(
      result.current.state?.status,
      `BUG #829: a {_timeout:true} payload means the server already closed the ` +
        `stream — the client must close too, not keep the EventSource open. ` +
        `Got status=${result.current.state?.status}.`,
    ).toBe("failed")

    unmount()
  })

  it("source treats unknown and _timeout as terminal (isTerminalPayload)", () => {
    const src = readSrc("hooks/use-process-stream.ts")
    // The close-set must be augmented with unknown + _timeout handling.
    expect(src).toMatch(/status\s*===\s*"unknown"/)
    expect(src).toMatch(/_timeout/)
    // Both must close the EventSource (not just setState).
    expect(src).toMatch(/es\.close\(\)/)
  })
})

// ---------------------------------------------------------------------------
// #830: DropZone MAX_SIZE must reflect pre-compression reality
// ---------------------------------------------------------------------------

describe("#830 DropZone pre-compression size gate", () => {
  it("MAX_SIZE is raised above the 50MB compressed cap (gate checks raw size)", () => {
    const src = readSrc("components/upload/drop-zone.tsx")
    // The old buggy gate: 50 * 1024 * 1024 — the pipeline compresses 6-10x
    // before upload, so the gate must allow a raw clip well above 50 MB.
    expect(src).not.toMatch(/MAX_SIZE\s*=\s*50\s*\*\s*1024\s*\*\s*1024/)
    // New realistic pre-compression ceiling (500 MB).
    expect(src).toMatch(/MAX_SIZE\s*=\s*500\s*\*\s*1024\s*\*\s*1024/)
  })

  it("drop-zone accept list drops .mkv (agrees with zip-parser VIDEO_EXTENSIONS)", () => {
    const src = readSrc("components/upload/drop-zone.tsx")
    // #822 parity: mkv unsupported by parseZip + render/compression path.
    // The ACCEPTED_EXTENSIONS literal must not contain mkv (comments about
    // removal are fine).
    const acceptLine = src.match(/ACCEPTED_EXTENSIONS\s*=\s*"([^"]*)"/)
    expect(acceptLine, "ACCEPTED_EXTENSIONS literal not found").not.toBeNull()
    expect(acceptLine?.[1]).not.toContain("mkv")
  })
})

// ---------------------------------------------------------------------------
// #831: Progress 0..1 must be scaled to 0..100 before reaching <Progress>
// ---------------------------------------------------------------------------

describe("#831 ProcessingBanner scales backend 0..1 progress to 0..100", () => {
  it("processing-banner normalizes raw progress via *100", () => {
    const src = readSrc("components/session/processing-banner.tsx")
    // Must scale raw 0..1 → 0..100 (rounded, clamped).
    expect(src).toMatch(/rawProgress\s*\*\s*100|progress\s*\*\s*100/)
    expect(src).toMatch(/Math\.round/)
    expect(src).toMatch(/Math\.min\(/)
  })

  it("Progress component invariant: 100 - value expects 0..100 (unchanged)", () => {
    const src = readFileSync(join(COMPONENTS_DIR, "ui", "progress.tsx"), "utf-8")
    // The indicator transform expects a 0..100 value; the fix is upstream in
    // the banner, not here. Confirm the contract still holds.
    expect(src).toMatch(/100\s*-\s*\(value\s*\|\|\s*0\)/)
  })

  it("gamification-panel already passes 0..100 (regression guard, not the bug site)", () => {
    const src = readSrc("components/gamification/gamification-panel.tsx")
    expect(src).toMatch(/\*\s*100/)
  })
})
