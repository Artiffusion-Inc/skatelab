import { describe, expect, it, beforeEach } from "vitest"
import { render } from "@/test/test-utils"
import { VideoWithSkeleton } from "../video-with-skeleton"
import { useAnalysisStore } from "@/stores/analysis"
import type { PhasesData, PoseData } from "@/types"

// RED repro: video-with-skeleton.tsx:63 handleTimeUpdate computes
//   frame = Math.floor((video.currentTime / video.duration) * totalFrames)
// with NO guard on duration=0 (→ Infinity) or duration=NaN (→ NaN).
// setCurrentFrame(NaN/Infinity) corrupts the shared zustand analysis store,
// consumed by ThreeJSkeletonViewer (frame selection) + FrameMetricsChart
// (Recharts ReferenceLine x=NaN). The sync effect at :35 guards
// `!video?.duration || Number.isNaN(video.duration)` — handleTimeUpdate does
// NOT mirror that guard.
//
// duration=0 reachable: empty/failed video source, OR timeupdate fires before
// loadedmetadata (duration still NaN/0 on some browsers).
//
// happy-dom <video> defaults duration to NaN (no media loaded). We render the
// component (poseData=null fallback path renders a bare <video> with
// onTimeUpdate={handleTimeUpdate}), then dispatch a timeupdate event on the
// rendered <video> element. currentTime defaults to 0; 0/NaN*totalFrames = NaN
// → setCurrentFrame(NaN) → store.currentFrame becomes NaN.

const mockPose: PoseData = {
  frames: [0, 10, 20],
  poses: [[[0, 0, 1]]],
  fps: 30,
}

const mockPhases: PhasesData = {
  takeoff: { frame: 30, timestamp: 1.0 },
  peak: { frame: 45, timestamp: 1.5 },
  landing: { frame: 60, timestamp: 2.0 },
}

describe("VideoWithSkeleton handleTimeUpdate NaN/Infinity (RED repro)", () => {
  beforeEach(() => {
    useAnalysisStore.setState({ currentFrame: 0 })
  })

  it("does not setCurrentFrame(NaN) when video.duration is NaN (pre-loadedmetadata timeupdate)", () => {
    const { container } = render(
      <VideoWithSkeleton
        videoUrl="https://example.com/video.mp4"
        poseData={mockPose}
        phases={mockPhases}
        totalFrames={120}
      />,
    )
    const video = container.querySelector("video") as HTMLVideoElement
    expect(video, "video element should render").not.toBeNull()

    // happy-dom: video.duration defaults to NaN (no metadata loaded).
    // Simulate a timeupdate that fires before loadedmetadata.
    video.currentTime = 3
    video.dispatchEvent(new Event("timeupdate"))

    const cf = useAnalysisStore.getState().currentFrame
    expect(
      Number.isNaN(cf),
      `BUG #1: handleTimeUpdate set currentFrame=NaN (video.duration=NaN). ` +
        `video-with-skeleton.tsx:63 Math.floor((currentTime/duration)*totalFrames) ` +
        `= Math.floor((3/NaN)*120) = NaN → setCurrentFrame(NaN) corrupts shared ` +
        `analysis store → ThreeJSkeletonViewer frame selection + FrameMetricsChart ` +
        `ReferenceLine x=NaN break. Sync effect :35 guards NaN/zero duration but ` +
        `handleTimeUpdate does NOT mirror the guard. duration=NaN reachable: ` +
        `timeupdate before loadedmetadata (no metadata yet) or empty/failed source.`,
    ).toBe(false)
    expect(cf, `BUG #1: currentFrame should stay 0 (or a finite clamped value), got ${cf}.`).toBe(0)
  })

  it("does not setCurrentFrame(Infinity) when video.duration is 0 (empty/failed source)", () => {
    const { container } = render(
      <VideoWithSkeleton videoUrl="" poseData={null} phases={null} totalFrames={120} />,
    )
    const video = container.querySelector("video") as HTMLVideoElement
    expect(video, "video element should render").not.toBeNull()

    // Force duration=0 (empty/failed source) and a non-zero currentTime so
    // (currentTime/0)*totalFrames = Infinity.
    Object.defineProperty(video, "duration", { value: 0, configurable: true })
    video.currentTime = 2
    video.dispatchEvent(new Event("timeupdate"))

    const cf = useAnalysisStore.getState().currentFrame
    expect(
      Number.isFinite(cf),
      `BUG #1: handleTimeUpdate set currentFrame=${cf} (video.duration=0). ` +
        `video-with-skeleton.tsx:63 Math.floor((2/0)*120) = Infinity → ` +
        `setCurrentFrame(Infinity) corrupts shared analysis store. ` +
        `duration=0 reachable: empty/failed video source.`,
    ).toBe(true)
    expect(cf, `BUG #1: currentFrame should stay 0 (finite), got ${cf}.`).toBe(0)
  })
})
