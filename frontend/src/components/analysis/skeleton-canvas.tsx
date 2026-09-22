"use client"

import { useLayoutEffect, useRef, useState, useCallback } from "react"
import type { PoseData } from "@/types"
import { nearestPoseIndex } from "./pose-data"
import { H36M_SKELETON_CONNECTIONS } from "./h36m-skeleton"

interface SkeletonCanvasProps {
  poseData: PoseData
  currentFrame: number
  width: number
  height: number
}

// H3.6M-17 joint colors
const JOINT_COLORS = [
  "#FF0000", // 0: hip_center (red)
  "#00FF00", // 1: r_hip (green)
  "#00FF00", // 2: r_knee
  "#00FF00", // 3: r_foot
  "#0000FF", // 4: l_hip (blue)
  "#0000FF", // 5: l_knee
  "#0000FF", // 6: l_foot
  "#FFFF00", // 7: spine (yellow)
  "#FFFF00", // 8: thorax
  "#FF00FF", // 9: neck (magenta)
  "#FF00FF", // 10: head
  "#00FFFF", // 11: l_shoulder (cyan)
  "#00FFFF", // 12: l_elbow
  "#00FFFF", // 13: l_wrist
  "#FFA500", // 14: r_shoulder (orange)
  "#FFA500", // 15: r_elbow
  "#FFA500", // 16: r_wrist
]

function drawAngleArc(
  ctx: CanvasRenderingContext2D,
  a: [number, number],
  b: [number, number],
  c: [number, number],
  width: number,
  height: number,
) {
  const angle = Math.atan2(c[1] - b[1], c[0] - b[0]) - Math.atan2(a[1] - b[1], a[0] - b[0])
  const startAngle = Math.atan2(a[1] - b[1], a[0] - b[0])
  const radius = 25
  ctx.beginPath()
  ctx.arc(b[0] * width, b[1] * height, radius, startAngle, startAngle + angle, angle < 0)
  ctx.strokeStyle = "rgba(255, 255, 255, 0.5)"
  ctx.lineWidth = 2
  ctx.stroke()
}

export function SkeletonCanvas({ poseData, currentFrame, width, height }: SkeletonCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const [hoverJoint, setHoverJoint] = useState<number | null>(null)
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      setMousePos({ x: mx, y: my })

      const frameIndex = nearestPoseIndex(poseData, currentFrame)
      if (frameIndex === -1) return
      const pose = poseData.poses[frameIndex]
      if (!pose) return

      let closest = -1
      let closestDist = Infinity
      for (let i = 0; i < pose.length; i++) {
        const joint = pose[i]
        if (!joint) continue
        const [x, y, conf] = joint
        if (conf < 0.3) continue
        const dx = x * width - mx
        const dy = y * height - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 20 && dist < closestDist) {
          closest = i
          closestDist = dist
        }
      }
      setHoverJoint(closest)
    },
    [currentFrame, poseData, width, height],
  )

  const handleMouseLeave = useCallback(() => setHoverJoint(null), [])

  // biome-ignore lint/correctness/useExhaustiveDependencies: mousePos required for tooltip redraw
  useLayoutEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Clear canvas
    ctx.clearRect(0, 0, width, height)

    // Find the frame index in sampled data
    const frameIndex = nearestPoseIndex(poseData, currentFrame)
    if (frameIndex === -1) return

    const pose = poseData.poses[frameIndex]
    if (!pose) return

    // Draw skeleton connections
    ctx.strokeStyle = "rgba(255, 255, 255, 0.6)"
    ctx.lineWidth = 2

    for (const [start, end] of H36M_SKELETON_CONNECTIONS) {
      const startJoint = pose[start]
      const endJoint = pose[end]

      if (!startJoint || !endJoint) continue

      const [x1, y1, conf1] = startJoint
      const [x2, y2, conf2] = endJoint

      if (conf1 < 0.3 || conf2 < 0.3) continue // Skip low-confidence joints

      ctx.beginPath()
      ctx.moveTo(x1 * width, y1 * height)
      ctx.lineTo(x2 * width, y2 * height)
      ctx.stroke()
    }

    // Draw knee angle arcs
    const rHip = pose[1]
    const rKnee = pose[2]
    const rAnkle = pose[3]
    if (rHip && rKnee && rAnkle) {
      drawAngleArc(
        ctx,
        [rHip[0], rHip[1]],
        [rKnee[0], rKnee[1]],
        [rAnkle[0], rAnkle[1]],
        width,
        height,
      )
    }

    const lHip = pose[4]
    const lKnee = pose[5]
    const lAnkle = pose[6]
    if (lHip && lKnee && lAnkle) {
      drawAngleArc(
        ctx,
        [lHip[0], lHip[1]],
        [lKnee[0], lKnee[1]],
        [lAnkle[0], lAnkle[1]],
        width,
        height,
      )
    }

    // Right hip angle: shoulder -> hip -> knee
    const rShoulderHip = pose[14]
    const rHipJoint = pose[1]
    const rKneeJoint = pose[2]
    if (rShoulderHip && rHipJoint && rKneeJoint) {
      drawAngleArc(
        ctx,
        [rShoulderHip[0], rShoulderHip[1]],
        [rHipJoint[0], rHipJoint[1]],
        [rKneeJoint[0], rKneeJoint[1]],
        width,
        height,
      )
    }

    // Left hip angle
    const lShoulderHip = pose[11]
    const lHipJoint = pose[4]
    const lKneeJoint = pose[5]
    if (lShoulderHip && lHipJoint && lKneeJoint) {
      drawAngleArc(
        ctx,
        [lShoulderHip[0], lShoulderHip[1]],
        [lHipJoint[0], lHipJoint[1]],
        [lKneeJoint[0], lKneeJoint[1]],
        width,
        height,
      )
    }

    // Trunk lean: hip -> spine -> neck
    const hipCenter = pose[0]
    const spineCenter = pose[7]
    const neckCenter = pose[9]
    if (hipCenter && spineCenter && neckCenter) {
      drawAngleArc(
        ctx,
        [hipCenter[0], hipCenter[1]],
        [spineCenter[0], spineCenter[1]],
        [neckCenter[0], neckCenter[1]],
        width,
        height,
      )
    }

    // Draw joints
    for (let i = 0; i < pose.length; i++) {
      const joint = pose[i]
      if (!joint) continue

      const [x, y, conf] = joint
      if (conf < 0.3) continue // Skip low-confidence joints

      ctx.beginPath()
      ctx.arc(x * width, y * height, 4, 0, Math.PI * 2)
      ctx.fillStyle = JOINT_COLORS[i] || "#FFFFFF"
      ctx.fill()
    }

    // Draw CoM (center of mass)
    const pelvis = pose[0]
    const thorax = pose[8]
    const neck = pose[9]
    const head = pose[10]
    if (pelvis && thorax && neck && head) {
      const [px, py] = pelvis
      const [tx, ty] = thorax
      const [nx, ny] = neck
      const [hx, hy] = head
      const comX = (px * 0.5 + tx * 0.3 + nx * 0.15 + hx * 0.05) * width
      const comY = (py * 0.5 + ty * 0.3 + ny * 0.15 + hy * 0.05) * height
      ctx.beginPath()
      ctx.arc(comX, comY, 6, 0, Math.PI * 2)
      ctx.fillStyle = "#ef4444"
      ctx.fill()
      ctx.strokeStyle = "#fff"
      ctx.lineWidth = 1
      ctx.stroke()
    }

    // Draw hover label
    if (hoverJoint !== null) {
      const joint = pose[hoverJoint]
      if (joint) {
        const [x, y] = joint
        const px = x * width
        const py = y * height
        ctx.font = "12px Inter, sans-serif"
        ctx.fillStyle = "rgba(0, 0, 0, 0.7)"
        const text = `Joint ${hoverJoint}`
        const tw = ctx.measureText(text).width
        ctx.fillRect(px + 8, py - 16, tw + 8, 20)
        ctx.fillStyle = "#fff"
        ctx.fillText(text, px + 12, py - 2)
      }
    }
  }, [poseData, currentFrame, width, height, hoverJoint, mousePos])

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className="absolute inset-0"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    />
  )
}
