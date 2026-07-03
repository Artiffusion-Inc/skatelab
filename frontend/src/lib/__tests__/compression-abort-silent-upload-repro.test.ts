import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useVideoCompression } from "../use-video-compression"

// RED repro: use-video-compression.ts abort = 60s-delayed silent upload of the
// uncompressed original.
//
// compress() returns a Promise resolved/rejected only by worker.onmessage /
// worker.onerror. abort() calls worker.terminate(), which fires NEITHER
// onmessage NOR onerror — so the compress promise NEVER settles; it hangs
// forever. In upload/page.tsx:108 the upload flow does
//   await Promise.race([compress(file), 60s-timeout])
// the 60s timeout rejects first → :121 catch → toast.info("compressionSkip") →
// :127 setStep("uploading") + uploads the ORIGINAL uncompressed file. So a user
// who clicks Cancel (abort → setStep("picked"), picker shown) THINKS they
// cancelled, but 60s later the app jumps to "uploading" and silently uploads the
// uncompressed original anyway. Cancel is a no-op that delays then defeats the
// user.
//
// This test asserts the root cause directly: after abort(), the compress promise
// must REJECT (cancel must settle the dangling promise). RED: the promise never
// settles because terminate() calls neither onmessage nor onerror, so no reject
// is ever invoked.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

// Controllable Worker mock. terminate() is a no-op (mirrors the real Worker API:
// terminate() does not fire onmessage/onerror). The test can fire onmessage /
// onerror manually if it wants, but the bug is that abort() does NOT do so.
let workers: MockWorker[] = []

class MockWorker {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  terminated = false

  constructor(_url: URL) {
    workers.push(this)
  }
  postMessage(_msg: unknown) {
    // no-op — the worker would normally process the compress request
  }
  terminate() {
    // Real Worker.terminate() does NOT fire onmessage or onerror. That is the
    // bug: the compress promise's resolve/reject are only reachable via those
    // handlers, so terminate() leaves the promise dangling forever.
    this.terminated = true
  }
}

beforeEach(() => {
  workers = []
  vi.stubGlobal("Worker", MockWorker)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useVideoCompression abort() does not settle compress promise (RED repro)", () => {
  it("compress promise rejects after abort() (not hang forever)", async () => {
    const { result } = renderHook(() => useVideoCompression())

    const file = new File([new Uint8Array(20 * 1024 * 1024)], "big.mp4", {
      type: "video/mp4",
    })

    // Start compression → returns a promise that only settles via worker handlers.
    const compressPromiseRef: { current: Promise<unknown> | null } = { current: null }
    act(() => {
      compressPromiseRef.current = result.current.compress(file)
    })
    const compressPromise = compressPromiseRef.current
    if (!compressPromise) throw new Error("compress() did not return a promise")

    await waitFor(() => expect(workers.length).toBeGreaterThanOrEqual(1))
    const worker =
      workers[0] ??
      (() => {
        throw new Error("no worker")
      })()
    expect(worker.onmessage).not.toBeNull()
    expect(worker.onerror).not.toBeNull()

    // #530: attach the rejection handler BEFORE calling abort() so the
    // synchronous reject in abort() lands on a handled promise. The
    // rejecter is then asserted via the captured error from .catch.
    let abortError: unknown = null
    compressPromise.catch(err => {
      abortError = err
    })
    // Yield so the .catch handler is registered before abort() runs.
    await Promise.resolve()

    // User clicks Cancel → abort() → worker.terminate() + reject.
    let abortCalled = false
    await act(async () => {
      result.current.abort()
      abortCalled = true
    })
    expect(abortCalled, "abort() was called").toBe(true)
    expect(worker.terminated, "abort() terminated the worker").toBe(true)

    // EXPECTED (fixed): abort() rejects the compress promise so the caller can
    // stop the flow. RED (bug): terminate() fires neither onmessage nor onerror,
    // so the promise NEVER settles — it hangs forever. Assert the captured
    // rejection (handler attached before abort) instead of `.rejects.toThrow()`
    // which races the synchronous reject.
    expect(abortError).toBeInstanceOf(Error)
    expect((abortError as Error).message).toBe("Compression aborted")
  }, 3000)
})
