import { describe, expect, it } from "vitest"
import smokeResult from "../../../../test-fixtures/ml-smoke-result.json"
import { parsePoseDataPayload } from "@/lib/api/sessions"

describe("session pose_data contract", () => {
  it("accepts the real smoke annotations at the API boundary", () => {
    const poseData = parsePoseDataPayload(
      { ...smokeResult.annotations, fps: smokeResult.video.fps },
      smokeResult.video.fps,
    )

    expect(poseData.frames).toEqual(smokeResult.annotations.frame_indices)
    expect(poseData.timestamps).toEqual(smokeResult.annotations.timestamps_s)
    expect(poseData.poses[0][0]).toEqual([
      smokeResult.annotations.poses[0][0][0],
      smokeResult.annotations.poses[0][0][1],
      smokeResult.annotations.confidence[0][0],
    ])
  })
})
