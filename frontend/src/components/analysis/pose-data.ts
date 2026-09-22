import type { PoseData } from "@/types"

interface InferenceAnnotations {
  keypoint_format: string
  coordinate_space: string
  frame_indices: number[]
  timestamps_s: number[]
  poses: Array<Array<number[] | null>>
  confidence: Array<Array<number | null>>
}

interface InferenceResult {
  video: { fps: number }
  annotations: InferenceAnnotations
}

function assertValidAnnotations(annotations: InferenceAnnotations, fps: number) {
  if (annotations.keypoint_format !== "h36m17") {
    throw new Error(`Unsupported keypoint format: ${annotations.keypoint_format}`)
  }
  if (annotations.coordinate_space !== "normalized") {
    throw new Error(`Unsupported coordinate space: ${annotations.coordinate_space}`)
  }
  if (!Number.isFinite(fps) || fps <= 0) throw new Error("Video FPS must be positive")
  if (
    annotations.frame_indices.length !== annotations.poses.length ||
    annotations.frame_indices.length !== annotations.timestamps_s.length ||
    annotations.frame_indices.length !== annotations.confidence.length
  ) {
    throw new Error("Annotation arrays must have the same frame count")
  }
  for (let index = 0; index < annotations.frame_indices.length; index++) {
    const frame = annotations.frame_indices[index]
    const timestamp = annotations.timestamps_s[index]
    if (!Number.isInteger(frame) || (index > 0 && frame <= annotations.frame_indices[index - 1])) {
      throw new Error("Annotation frame indices must be strictly increasing integers")
    }
    if (
      !Number.isFinite(timestamp) ||
      timestamp < 0 ||
      (index > 0 && timestamp <= annotations.timestamps_s[index - 1])
    ) {
      throw new Error("Annotation timestamps must be strictly increasing and non-negative")
    }
    if (annotations.poses[index].length !== 17 || annotations.confidence[index].length !== 17) {
      throw new Error("H3.6M annotations must contain 17 keypoints per frame")
    }
  }
}

export function poseDataFromAnnotations(annotations: InferenceAnnotations, fps: number): PoseData {
  assertValidAnnotations(annotations, fps)
  return {
    frames: annotations.frame_indices,
    timestamps: annotations.timestamps_s,
    fps,
    poses: annotations.poses.map((frame, frameIndex) =>
      frame.map((point, keypointIndex) => {
        if (!point) return null
        if (point.length !== 2) throw new Error("H3.6M 2D keypoints must contain x and y")
        const [x, y] = point
        if (![x, y].every(value => Number.isFinite(value) && value >= 0 && value <= 1)) {
          throw new Error("Normalized pose coordinates must be finite values in [0, 1]")
        }
        const confidence = annotations.confidence[frameIndex][keypointIndex]
        return [
          x,
          y,
          confidence === null || !Number.isFinite(confidence)
            ? 0
            : Math.min(1, Math.max(0, confidence)),
        ]
      }),
    ),
  }
}

export function poseDataFromInferenceResult(result: InferenceResult): PoseData {
  return poseDataFromAnnotations(result.annotations, result.video.fps)
}

function nearestIndex(values: number[], target: number): number {
  if (values.length === 0) return -1
  let low = 0
  let high = values.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (values[middle] === target) return middle
    if (values[middle] < target) low = middle + 1
    else high = middle - 1
  }
  if (low === 0) return 0
  if (low === values.length) return values.length - 1
  return target - values[low - 1] <= values[low] - target ? low - 1 : low
}

export function nearestPoseIndex(poseData: PoseData, frame: number): number {
  return nearestIndex(poseData.frames, frame)
}

export function frameToTime(poseData: PoseData, frame: number): number {
  if (poseData.frames.length === 0) return 0
  if (!poseData.timestamps?.length) return Math.max(0, frame) / poseData.fps

  const clampedFrame = Math.max(poseData.frames[0], frame)
  if (clampedFrame <= poseData.frames[0]) return poseData.timestamps[0]
  const last = poseData.frames.length - 1
  if (clampedFrame >= poseData.frames[last]) return poseData.timestamps[last]

  const right = poseData.frames.findIndex(value => value >= clampedFrame)
  if (poseData.frames[right] === clampedFrame) return poseData.timestamps[right]
  const left = right - 1
  const ratio =
    (clampedFrame - poseData.frames[left]) / (poseData.frames[right] - poseData.frames[left])
  return (
    poseData.timestamps[left] + ratio * (poseData.timestamps[right] - poseData.timestamps[left])
  )
}

export function timeToFrame(poseData: PoseData, time: number): number {
  const values = poseData.timestamps ?? poseData.frames.map(frame => frame / poseData.fps)
  const index = nearestIndex(values, Math.max(0, time))
  return index < 0 ? 0 : poseData.frames[index]
}
