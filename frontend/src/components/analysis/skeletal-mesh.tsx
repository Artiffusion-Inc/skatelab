/// <reference path="../../../react-three.d.ts" />
"use client"

import type {} from "@react-three/fiber"
import { Line } from "@react-three/drei"
import { useMemo } from "react"
import * as THREE from "three"
import type { FrameMetrics, PoseData } from "@/types"
import { useAnalysisStore } from "@/stores/analysis"
import { JointLabel } from "./joint-label"

interface BoneProps {
  start: [number, number, number]
  end: [number, number, number]
}

function Bone({ start, end }: BoneProps) {
  const points = useMemo(
    () => [new THREE.Vector3(...start), new THREE.Vector3(...end)],
    [start, end],
  )
  return <Line points={points} color="#cccccc" lineWidth={3} />
}

interface JointProps {
  position: [number, number, number]
  color: number
  onPointerOver?: () => void
  onPointerOut?: () => void
}

function Joint({ position, color, onPointerOver, onPointerOut }: JointProps) {
  // Use a small point for joints instead of sphere
  const points = useMemo(() => [new THREE.Vector3(...position)], [position])
  return (
    <Line
      points={points}
      color={`#${color.toString(16).padStart(6, "0")}`}
      lineWidth={8}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
    />
  )
}

function SolidJoint({ position, color, onPointerOver, onPointerOut }: JointProps) {
  const mesh = useMemo(() => {
    const geometry = new THREE.SphereGeometry(0.015, 8, 8)
    const material = new THREE.MeshStandardMaterial({
      color: `#${color.toString(16).padStart(6, "0")}`,
    })
    const m = new THREE.Mesh(geometry, material)
    m.position.set(...position)
    return m
  }, [position, color])

  return <primitive object={mesh} onPointerOver={onPointerOver} onPointerOut={onPointerOut} />
}

interface SkeletalMeshProps {
  poseData: PoseData
  frameMetrics: FrameMetrics | null
  currentFrame: number
  renderMode: "wireframe" | "solid"
}

// H3.6M 17-keypoint skeleton connections (same as 2D)
const CONNECTIONS = [
  // Right leg
  [0, 1],
  [1, 2],
  [2, 3],
  // Left leg
  [0, 4],
  [4, 5],
  [5, 6],
  // Spine + head
  [0, 7],
  [7, 8],
  [8, 9],
  [9, 10],
  // Left arm
  [9, 11],
  [11, 12],
  [12, 13],
  // Right arm
  [9, 14],
  [14, 15],
  [15, 16],
]

// Color coding based on joint angle quality
function getJointColor(
  jointIndex: number,
  frameMetrics: FrameMetrics | null,
  currentFrame: number,
  // #527: pass sampled frames array to resolve absolute frame → sampled
  // index via indexOf (matches the pattern at line 134). Math.min clamp
  // was freezing colors on the last sampled entry for the entire
  // playback after ~1s.
  sampledFrames: number[] | null = null,
): number {
  if (!frameMetrics) return 0xc8c8c8 // Default gray

  // Map joint index to metric (simplified)
  let metric: (number | null)[] | null = null
  if (jointIndex <= 3)
    metric = frameMetrics.knee_angles_r // Right leg
  else if (jointIndex <= 6)
    metric = frameMetrics.knee_angles_l // Left leg
  else if (jointIndex >= 11 && jointIndex <= 13)
    // #527: arm joints share the L/R-suffix with the matching side comment.
    // Was inverted: left arm read hip_angles_r (right hip), right arm read
    // hip_angles_l (left hip). Note: arms ideally need arm-angle metrics;
    // FrameMetrics has none, so hip flexion is a stand-in. L/R is the
    // minimum correction — see issue for future arm-metric work.
    metric = frameMetrics.hip_angles_l // Left arm
  else if (jointIndex >= 14) metric = frameMetrics.hip_angles_r // Right arm

  if (!metric || metric.length === 0) return 0xc8c8c8

  // #527: resolve absolute frame → sampled index via indexOf (mirrors
  // line 134). Math.min(currentFrame, metric.length - 1) was pinning
  // every frame above ~29 to the last sampled entry, freezing joint
  // colors for the entire playback after ~1s.
  let frameIdx = 0
  if (sampledFrames) {
    const idx = sampledFrames.indexOf(currentFrame)
    if (idx !== -1) frameIdx = idx
  } else {
    frameIdx = Math.min(currentFrame, metric.length - 1)
  }
  const angle = metric[frameIdx]

  if (angle === null || angle === undefined) return 0xc8c8c8

  // Color coding: green (90-170°), yellow (60-190°), red (outside)
  if (angle >= 90 && angle <= 170) return 0x4ade80 // Green
  if (angle >= 60 && angle <= 190) return 0xfacc15 // Yellow
  return 0xef4444 // Red
}

export function SkeletalMesh({
  poseData,
  frameMetrics,
  currentFrame,
  renderMode,
}: SkeletalMeshProps) {
  const { hoveredJoint, setHoveredJoint } = useAnalysisStore()

  const { joints, bones } = useMemo(() => {
    // Find the frame index in sampled data
    const frameIndex = poseData.frames.indexOf(currentFrame)
    if (frameIndex === -1) return { joints: [], bones: [] }

    const pose = poseData.poses[frameIndex]
    if (!pose) return { joints: [], bones: [] }

    // Convert normalized [0,1] to 3D space [-0.5, 0.5]
    const scale = 1.0
    const jointPositions: Array<{
      index: number
      position: [number, number, number]
      color: number
    }> = []
    const bonePositions: Array<{
      index: number
      start: [number, number, number]
      end: [number, number, number]
    }> = []

    // First pass: collect all joint positions
    for (let i = 0; i < pose.length; i++) {
      const [x, y, conf] = pose[i]
      if (conf < 0.3) continue // Skip low-confidence joints

      jointPositions.push({
        index: i,
        position: [(x - 0.5) * scale, (y - 0.5) * scale, 0],
        color: getJointColor(i, frameMetrics, currentFrame, poseData.frames),
      })
    }

    // Second pass: create bones
    for (let boneIdx = 0; boneIdx < CONNECTIONS.length; boneIdx++) {
      const [start, end] = CONNECTIONS[boneIdx]
      const startJoint = pose[start]
      const endJoint = pose[end]

      if (!startJoint || !endJoint) continue

      const [x1, y1, conf1] = startJoint
      const [x2, y2, conf2] = endJoint

      if (conf1 < 0.3 || conf2 < 0.3) continue // Skip low-confidence joints

      bonePositions.push({
        index: boneIdx,
        start: [(x1 - 0.5) * scale, (y1 - 0.5) * scale, 0],
        end: [(x2 - 0.5) * scale, (y2 - 0.5) * scale, 0],
      })
    }

    return { joints: jointPositions, bones: bonePositions }
  }, [poseData, frameMetrics, currentFrame])

  const hoveredJointData = hoveredJoint !== null ? joints.find(j => j.index === hoveredJoint) : null

  return (
    <>
      {/* Bones */}
      {bones.map(bone => (
        <Bone
          key={`bone-${bone.index}`}
          start={bone.start as [number, number, number]}
          end={bone.end as [number, number, number]}
        />
      ))}

      {/* Joints */}
      {joints.map(joint =>
        renderMode === "solid" ? (
          <SolidJoint
            key={`joint-${joint.index}`}
            position={joint.position as [number, number, number]}
            color={joint.color}
            onPointerOver={() => setHoveredJoint(joint.index)}
            onPointerOut={() => setHoveredJoint(null)}
          />
        ) : (
          <Joint
            key={`joint-${joint.index}`}
            position={joint.position as [number, number, number]}
            color={joint.color}
            onPointerOver={() => setHoveredJoint(joint.index)}
            onPointerOut={() => setHoveredJoint(null)}
          />
        ),
      )}

      {hoveredJointData && (
        <JointLabel
          jointIndex={hoveredJointData.index}
          position={new THREE.Vector3(...hoveredJointData.position)}
        />
      )}
    </>
  )
}
