import { describe, expect, it } from "vitest"
import { H36M_SKELETON_CONNECTIONS } from "./h36m-skeleton"

describe("H36M_SKELETON_CONNECTIONS", () => {
  it("matches the ML H3.6M-17 topology", () => {
    expect(H36M_SKELETON_CONNECTIONS).toEqual([
      [0, 7],
      [7, 8],
      [8, 9],
      [9, 10],
      [0, 1],
      [1, 2],
      [2, 3],
      [0, 4],
      [4, 5],
      [5, 6],
      [8, 14],
      [14, 15],
      [15, 16],
      [8, 11],
      [11, 12],
      [12, 13],
    ])
  })
})
