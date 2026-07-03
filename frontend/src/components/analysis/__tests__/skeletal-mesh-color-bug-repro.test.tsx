import { describe, expect, it, vi, beforeEach } from "vitest"
import { render } from "@/test/test-utils"
import { useAnalysisStore } from "@/stores/analysis"
import type { FrameMetrics, PoseData } from "@/types"

// RED repro: skeletal-mesh.tsx getJointColor has two bugs.
//
// BUG #1 (skeletal-mesh.tsx:106-108): arm joints colored by the WRONG metric
// (hip angles, not arm angles) AND L/R swapped.
//   joints 11-13 ("Left arm" per CONNECTIONS comment) → frameMetrics.hip_angles_r
//   joints 14+  ("Right arm")              → frameMetrics.hip_angles_l
// The comments self-contradict the _r/_l suffix (copy-paste inversion). Arms
// are colored by hip flexion — biomechanically meaningless — and the left/right
// sides are swapped. Sibling frame-metrics-chart.tsx:43-44 maps
// hip_angles_r→right hip correctly; skeletal-mesh is the sole swapped consumer.
//
// BUG #2 (skeletal-mesh.tsx:113): Math.min(currentFrame, metric.length - 1)
// clamps the ABSOLUTE video frame (0..totalFrames, e.g. 3000) against the
// SAMPLED metric array length (~30). Every frame above ~29 pins to the last
// sampled entry → joint color FROZEN for the entire playback after the first
// ~1s. Correct: resolve currentFrame → sampled index via
// poseData.frames.indexOf(currentFrame) (exactly as the component already does
// at :134 for pose selection).
//
// getJointColor is module-internal (not exported), so we render SkeletalMesh in
// wireframe mode and capture the color prop drei <Line> receives for each
// joint. The pose contains only the joints under test so captured <Line> color
// calls map 1:1 to joint indices. Color band (skeletal-mesh.tsx:119-121):
//   green 0x4ade80 for 90..170, yellow 0xfacc15 for 60..190, red 0xef4444 else.

// Capture every color drei <Line> is rendered with. Joint bones also render
// <Line> with color "#cccccc" (bones) — we filter those out by hex length.
const lineRenders: Array<{ color: string }> = []
vi.mock("@react-three/drei", () => ({
  Line: (props: { color?: string }) => {
    if (props.color && props.color !== "#cccccc") {
      lineRenders.push({ color: props.color })
    }
    return null
  },
}))

// joint-label renders nothing meaningful here; stub it so it never reaches
// drei/three internals.
vi.mock("../joint-label", () => ({
  JointLabel: () => null,
}))

import { SkeletalMesh } from "../skeletal-mesh"

// Build a pose with ONLY the joints under test present at confidence 1.
// H3.6M indices: 11 = left shoulder/elbow region (left arm start),
// 14 = right arm start. Joints 7,8,9,10 are spine/head (skipped to keep the
// captured <Line> color list = just joint colors).
function poseWith(joints: Array<[number, number]>) {
  // 17 keypoints, default [0,0,0] (conf 0 → skipped). Place requested joints.
  const pose: Array<[number, number, number]> = Array.from(
    { length: 17 },
    () => [0, 0, 0],
  )
  for (const [idx, [x, y]] of joints) pose[idx] = [x, y, 1]
  return pose
}

function hex(n: number) {
  return "#" + n.toString(16).padStart(6, "0")
}

const GREEN = 0x4ade80 // angle in 90..170
const RED = 0xef4444 // angle outside 60..190

describe("SkeletalMesh getJointColor (RED repro)", () => {
  beforeEach(() => {
    lineRenders.length = 0
    useAnalysisStore.setState({ currentFrame: 0 })
  })

  it("BUG #1: left-arm joint 11 uses hip_angles_L (left, matching 'Left arm' comment), NOT hip_angles_r", () => {
    // Asymmetric hip angles: LEFT hip green (100°), RIGHT hip red (200°).
    // Correct behavior: joint 11 ("Left arm") → hip_angles_l[0]=100 → green.
    // BUG: joint 11 uses hip_angles_r[0]=200 → red.
    const frameMetrics: FrameMetrics = {
      knee_angles_r: [],
      knee_angles_l: [],
      hip_angles_r: [200], // RIGHT hip → red
      hip_angles_l: [100], // LEFT hip → green
      trunk_lean: [],
      com_height: [],
    }
    const poseData: PoseData = {
      frames: [0],
      poses: [poseWith([[11, [0.4, 0.5]], [14, [0.6, 0.5]]])],
      fps: 30,
    }

    render(
      <SkeletalMesh
        poseData={poseData}
        frameMetrics={frameMetrics}
        currentFrame={0}
        renderMode="wireframe"
      />,
    )

    // Joints render in pose order: joint 11 first, then joint 14.
    const joint11Color = lineRenders[0]?.color
    const msg1 =
      "BUG #1: joint 11 ('Left arm', skeletal-mesh.tsx:106-107) colored " +
      String(joint11Color) +
      " — uses frameMetrics.hip_angles_r[0]=200 (RIGHT hip) → " +
      "red. Should use hip_angles_l[0]=100 (LEFT hip, matching the 'Left arm' " +
      "comment) → green " + hex(GREEN) + ". L/R swapped + arms colored by hip angles " +
      "(biomechanically meaningless). Sibling frame-metrics-chart.tsx:43-44 " +
      "maps hip_angles_r→right hip correctly."
    expect(joint11Color, msg1).toBe(hex(GREEN))
  })

  it("BUG #1: right-arm joint 14 uses hip_angles_R (right, matching 'Right arm' comment), NOT hip_angles_l", () => {
    // LEFT hip green (100°), RIGHT hip red (200°).
    // Correct: joint 14 ("Right arm") → hip_angles_r[0]=200 → red.
    // BUG: joint 14 uses hip_angles_l[0]=100 → green.
    const frameMetrics: FrameMetrics = {
      knee_angles_r: [],
      knee_angles_l: [],
      hip_angles_r: [200], // RIGHT hip → red
      hip_angles_l: [100], // LEFT hip → green
      trunk_lean: [],
      com_height: [],
    }
    const poseData: PoseData = {
      frames: [0],
      poses: [poseWith([[11, [0.4, 0.5]], [14, [0.6, 0.5]]])],
      fps: 30,
    }

    render(
      <SkeletalMesh
        poseData={poseData}
        frameMetrics={frameMetrics}
        currentFrame={0}
        renderMode="wireframe"
      />,
    )

    const joint14Color = lineRenders[1]?.color
    const msg2 =
      "BUG #1: joint 14 ('Right arm', skeletal-mesh.tsx:108) colored " +
      String(joint14Color) +
      " — uses frameMetrics.hip_angles_l[0]=100 (LEFT hip) → " +
      "green. Should use hip_angles_r[0]=200 (RIGHT hip, matching the 'Right " +
      "arm' comment) → red " + hex(RED) + ". L/R swapped."
    expect(joint14Color, msg2).toBe(hex(RED))
  })

  it("BUG #2: currentFrame=1500 (absolute) resolves to sampled index via poseData.frames, NOT Math.min clamp to last sampled", () => {
    // 30 sampled frames spanning absolute 0..2900 (step 100).
    const frames = Array.from({ length: 30 }, (_, i) => i * 100) // 0,100,...,2900
    // At absolute currentFrame=1500 → poseData.frames.indexOf(1500)=15.
    // Correct: getJointColor reads metric[15]=100 → green.
    // BUG: Math.min(1500, 29)=29 → reads metric[29]=200 → red (frozen on last).
    const hipR = frames.map((_, i) => (i === 15 ? 100 : 200)) // [15]=green, rest red
    // #527: BUG #2 is the frame-index clamp; L/R is BUG #1. After the
    // L/R fix joint 11 reads hip_angles_l (left arm). Set BOTH arrays
    // to [15]=100 so test 3 stays BUG-2-only regardless of L/R choice.
    const hipL = frames.map((_, i) => (i === 15 ? 100 : 200))
    const frameMetrics: FrameMetrics = {
      knee_angles_r: [],
      knee_angles_l: [],
      hip_angles_r: hipR,
      hip_angles_l: hipL,
      trunk_lean: [],
      com_height: [],
    }
    const poseData: PoseData = {
      frames,
      // pose at sampled index 15 (absolute frame 1500) has joint 11 present.
      poses: frames.map((_, i) =>
        i === 15 ? poseWith([[11, [0.4, 0.5]]]) : poseWith([]),
      ),
      fps: 30,
    }

    useAnalysisStore.setState({ currentFrame: 1500 })
    render(
      <SkeletalMesh
        poseData={poseData}
        frameMetrics={frameMetrics}
        currentFrame={1500}
        renderMode="wireframe"
      />,
    )

    const joint11Color = lineRenders[0]?.color
    const msg3 =
      "BUG #2: joint 11 at currentFrame=1500 colored " + String(joint11Color) + ". " +
      "skeletal-mesh.tsx:113 Math.min(currentFrame, metric.length-1) = " +
      "Math.min(1500, 29) = 29 → reads hip_angles_r[29]=200 → red (frozen on " +
      "last sampled frame). Should resolve currentFrame→sampled index via " +
      "poseData.frames.indexOf(1500)=15 → hip_angles_r[15]=100 → green " +
      hex(GREEN) + " (component already does this at :134 for pose selection). " +
      "Clamp pins EVERY frame above ~29 to the last sampled entry → joint " +
      "color frozen for entire playback after first ~1s."
    expect(joint11Color, msg3).toBe(hex(GREEN))
  })
})