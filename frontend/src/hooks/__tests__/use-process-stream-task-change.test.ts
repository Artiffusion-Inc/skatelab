import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { useProcessStream } from "../use-process-stream"

class MockEventSource {
  static instances: MockEventSource[] = []
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false
  url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }
}

describe("useProcessStream task changes", () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal("EventSource", MockEventSource)
  })

  afterEach(() => vi.unstubAllGlobals())

  it("closes the old stream and subscribes to the retried task", async () => {
    const { rerender, unmount } = renderHook(
      ({ taskId }: { taskId: string | null }) => useProcessStream(taskId),
      { initialProps: { taskId: "task-1" } },
    )

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    const first = MockEventSource.instances[0]

    rerender({ taskId: "task-2" })

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(2))
    expect(first.closed).toBe(true)
    expect(MockEventSource.instances[1].url).toContain("/process/task-2/stream")
    unmount()
  })
})
