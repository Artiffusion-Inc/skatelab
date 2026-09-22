import { describe, expect, it } from "vitest"
import smokeResult from "../../../test-fixtures/ml-smoke-result.json"
import {
  frameToTime,
  nearestPoseIndex,
  poseDataFromInferenceResult,
  timeToFrame,
} from "./pose-data"

describe("poseDataFromInferenceResult", () => {
  it("adapts the real ML smoke H3.6M-17 annotations without changing frame timing", () => {
    const poseData = poseDataFromInferenceResult(smokeResult)
    const annotations = smokeResult.annotations

    expect(smokeResult.schema_version).toBe("skatelab.inference.v1")
    expect(annotations.keypoint_format).toBe("h36m17")
    expect(annotations.coordinate_space).toBe("normalized")
    expect(poseData.frames).toEqual(annotations.frame_indices)
    expect(poseData.timestamps).toEqual(annotations.timestamps_s)
    expect(poseData.fps).toBe(smokeResult.video.fps)
    expect(poseData.poses).toHaveLength(smokeResult.processed_frames)
    expect(poseData.poses[0]).toHaveLength(17)
    expect(poseData.poses[0][0]).toEqual([
      annotations.poses[0][0][0],
      annotations.poses[0][0][1],
      annotations.confidence[0][0],
    ])
  })

  it("uses the nearest sampled pose while keeping the absolute video frame", () => {
    const fullPoseData = poseDataFromInferenceResult(smokeResult)
    const sampledFrames = fullPoseData.frames.filter((_, index) => index % 10 === 0)
    const sampledPoseData = {
      ...fullPoseData,
      frames: sampledFrames,
      poses: sampledFrames.map(frame => fullPoseData.poses[frame]),
      timestamps: sampledFrames.map(frame => fullPoseData.timestamps?.[frame] ?? 0),
    }

    expect(nearestPoseIndex(sampledPoseData, 44)).toBe(4)
    expect(sampledPoseData.frames[nearestPoseIndex(sampledPoseData, 44)]).toBe(40)
  })

  it("maps video time to the nearest annotated frame and back", () => {
    const poseData = poseDataFromInferenceResult(smokeResult)
    const frame = timeToFrame(poseData, smokeResult.annotations.timestamps_s[50])

    expect(frame).toBe(smokeResult.annotations.frame_indices[50])
    expect(frameToTime(poseData, frame)).toBe(smokeResult.annotations.timestamps_s[50])
  })
})
