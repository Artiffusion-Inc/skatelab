import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useProcessStream } from "../use-process-stream"

// RED repro: use-process-stream.ts SSE lifecycle has two bugs.
//
// Bug A (no reconnect): es.onerror = () => { setIsConnected(false); es.close() }
//   — permanent close, NO reconnect. A single transient network blip (timeout,
//   proxy idle drop) or the backend 60s inactivity timeout kills the stream
//   forever. ProcessingBanner has no fallback to poll /process/{id}/status, so
//   progress freezes ("analyzing 42%") until the 10-min isStale heuristic.
//
// Bug B (no JSON.parse guard): es.onmessage = e => { const data = JSON.parse(e.data); ... }
//   — malformed SSE frame throws inside onmessage, crashing the handler. No
//   try/catch around JSON.parse.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

// Controllable EventSource mock. Each instance records itself on a list so the
// test can fire onerror/onmessage and count how many times the constructor was
// called (reconnect = >1 construction for the same taskId).
let instances: MockEventSource[] = []
let ctorCallCount = 0

class MockEventSource {
  url: string
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  readyState = 0
  closed = false

  constructor(url: string) {
    this.url = url
    ctorCallCount += 1
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
  fireError() {
    this.onerror?.(new Event("error"))
  }
}

beforeEach(() => {
  instances = []
  ctorCallCount = 0
  vi.stubGlobal("EventSource", MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useProcessStream SSE onerror no-reconnect (RED repro)", () => {
  it("attempts reconnect after a transient onerror (not permanent close)", async () => {
    const { unmount } = renderHook(() => useProcessStream("task-1"))

    // EventSource constructed on mount.
    await waitFor(() => expect(instances.length).toBeGreaterThanOrEqual(1))
    const es = instances[0]!
    es.fireOpen()
    expect(es.closed).toBe(false)

    // Transient network blip → onerror.
    act(() => {
      es.fireError()
    })

    // Bug A: onerror permanently closes with NO reconnect. A fix would either
    // re-instantiate EventSource (ctorCallCount increases) or recover
    // isConnected. RED: ctorCallCount stays at 1 (no reconnect) and the stream
    // is permanently closed.
    await waitFor(() => expect(es.closed).toBe(true))

    // #525: wait for the reconnect timer (exponential backoff ~500ms+jitter)
    // to fire and construct a new EventSource. If no reconnect, ctorCallCount
    // stays at 1 and this times out.
    await waitFor(() => expect(ctorCallCount).toBeGreaterThan(1), { timeout: 3000 })

    expect(
      ctorCallCount,
      `BUG A: use-process-stream.ts:38-41 es.onerror permanently closes with NO ` +
        `reconnect. ctorCallCount=${ctorCallCount} (expected >1 for a reconnect). ` +
        `Single transient network blip / backend 60s inactivity timeout kills the ` +
        `stream forever; ProcessingBanner has no fallback to poll /process/{id}/status; ` +
        `stale "analyzing 42%" until 10-min isStale.`,
    ).toBeGreaterThan(1)

    unmount()
  })
})

describe("useProcessStream SSE onmessage malformed JSON (RED repro)", () => {
  it("does not throw on a malformed SSE data frame", async () => {
    const { unmount } = renderHook(() => useProcessStream("task-2"))

    await waitFor(() => expect(instances.length).toBeGreaterThanOrEqual(1))
    const es = instances[0]!
    es.fireOpen()

    // Bug B: onmessage does `const data = JSON.parse(e.data)` with no try/catch.
    // A malformed SSE frame throws and crashes the handler.
    expect(
      () =>
        act(() => {
          es.fireMessage("{malformed json")
        }),
      `BUG B: use-process-stream.ts:31 onmessage has no JSON.parse guard. ` +
        `Malformed SSE frame "{malformed json" throws inside onmessage, crashing ` +
        `the handler. No try/catch around JSON.parse.`,
    ).not.toThrow()

    // After a malformed frame the handler must remain alive for subsequent
    // valid frames (proving it did not crash the SSE subscription).
    let alive = false
    try {
      act(() => {
        es.fireMessage(JSON.stringify({ status: "processing", progress: 50, message: "ok" }))
      })
      alive = true
    } catch {
      alive = false
    }
    expect(
      alive,
      `BUG B: after the malformed frame the handler is dead — a subsequent valid ` +
        `frame cannot be processed because onmessage crashed with no try/catch.`,
    ).toBe(true)

    unmount()
  })
})
