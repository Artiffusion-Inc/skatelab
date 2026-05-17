import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import { usePageStatus } from "../use-page-status"

describe("usePageStatus", () => {
  it("returns loading when any query is pending", () => {
    const result = renderHook(() => usePageStatus([{ status: "pending" }, { status: "success" }]))
    expect(result.result.current.isLoading).toBe(true)
    expect(result.result.current.isError).toBe(false)
  })

  it("returns error when any query has error", () => {
    const err = new Error("fail")
    const result = renderHook(() =>
      usePageStatus([{ status: "error", error: err }, { status: "success" }]),
    )
    expect(result.result.current.isError).toBe(true)
    expect(result.result.current.error).toBeInstanceOf(Error)
  })

  it("returns success when all queries succeeded", () => {
    const result = renderHook(() => usePageStatus([{ status: "success" }, { status: "success" }]))
    expect(result.result.current.isLoading).toBe(false)
    expect(result.result.current.isError).toBe(false)
  })

  it("handles empty array", () => {
    const result = renderHook(() => usePageStatus([]))
    expect(result.result.current.isLoading).toBe(false)
    expect(result.result.current.isError).toBe(false)
  })

  it("returns isFirstLoad when a pending query has no cached data", () => {
    const result = renderHook(() =>
      usePageStatus([{ status: "pending" }, { status: "success", data: { id: 1 } }]),
    )
    expect(result.result.current.isFirstLoad).toBe(true)
  })

  it("does not return isFirstLoad when a pending query has cached data (refetch)", () => {
    const result = renderHook(() =>
      usePageStatus([
        { status: "pending", data: { id: 1 } },
        { status: "success", data: { id: 2 } },
      ]),
    )
    expect(result.result.current.isFirstLoad).toBe(false)
  })

  it("returns the first error when multiple queries have errors", () => {
    const err1 = new Error("first")
    const err2 = new Error("second")
    const result = renderHook(() =>
      usePageStatus([
        { status: "error", error: err1 },
        { status: "error", error: err2 },
      ]),
    )
    expect(result.result.current.error).toBe(err1)
  })

  it("returns null error when no queries have errors", () => {
    const result = renderHook(() => usePageStatus([{ status: "success" }]))
    expect(result.result.current.error).toBeNull()
  })
})
