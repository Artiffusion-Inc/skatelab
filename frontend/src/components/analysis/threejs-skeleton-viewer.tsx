/// <reference path="../../../react-three.d.ts" />
"use client"

import { Environment, Grid, OrbitControls, PerspectiveCamera } from "@react-three/drei"
import { Canvas, useThree } from "@react-three/fiber"
import { Suspense, useEffect } from "react"
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react"
import { useTranslations } from "@/i18n"
import { useAnalysisStore } from "@/stores/analysis"
import type { FrameMetrics, PoseData } from "@/types"
import { SkeletalMesh } from "./skeletal-mesh"

interface ThreeJSkeletonViewerProps {
  poseData: PoseData
  frameMetrics: FrameMetrics | null
  className?: string
}

function LoadingFallback() {
  const t = useTranslations("analysis")
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      {t("loading3D")}
    </div>
  )
}

const CAMERA_PRESETS = {
  front: {
    position: [0, 0, 1.5] as [number, number, number],
    target: [0, 0, 0] as [number, number, number],
  },
  side: {
    position: [1.5, 0, 0] as [number, number, number],
    target: [0, 0, 0] as [number, number, number],
  },
  top: {
    position: [0, 1.5, 0] as [number, number, number],
    target: [0, 0, 0] as [number, number, number],
  },
}

function CameraController() {
  const { camera } = useThree()
  const { cameraPreset } = useAnalysisStore()

  useEffect(() => {
    const preset = CAMERA_PRESETS[cameraPreset]
    if (preset) {
      camera.position.set(...preset.position)
      camera.lookAt(...preset.target)
      camera.updateProjectionMatrix()
    }
  }, [camera, cameraPreset])

  return null
}

function Scene({
  poseData,
  frameMetrics,
}: {
  poseData: PoseData
  frameMetrics: FrameMetrics | null
}) {
  const { currentFrame, renderMode } = useAnalysisStore()

  return (
    <>
      <CameraController />
      <PerspectiveCamera makeDefault position={[0, 0, 1.5]} fov={50} />
      <OrbitControls
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={0.5}
        maxDistance={3}
        target={[0, 0, 0]}
      />

      {/* Lighting using Environment */}
      <Environment preset="city" />

      {/* Skeleton */}
      <SkeletalMesh
        poseData={poseData}
        frameMetrics={frameMetrics}
        currentFrame={currentFrame}
        renderMode={renderMode}
      />

      {/* Grid helper */}
      <Grid
        args={[1, 10, 0x444444, 0x222222]}
        position={[0, -0.3, 0]}
        cellColor="#444444"
        sectionColor="#222222"
      />
    </>
  )
}

function CameraPresets() {
  const { cameraPreset, setCameraPreset } = useAnalysisStore()
  const t = useTranslations("analysis")
  const presets: Array<{ key: "front" | "side" | "top"; label: string }> = [
    { key: "front", label: t("viewFront") },
    { key: "side", label: t("viewSide") },
    { key: "top", label: t("viewTop") },
  ]
  return (
    <div
      className="absolute top-2 left-2 flex gap-1 rounded-lg p-1"
      style={{ backgroundColor: "oklch(var(--background) / 0.7)" }}
    >
      {presets.map(p => (
        <button
          key={p.key}
          type="button"
          onClick={() => setCameraPreset(p.key)}
          className={`rounded-md px-2 py-1 text-xs ${cameraPreset === p.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
        >
          {p.label}
        </button>
      ))}
    </div>
  )
}

function RenderModeToggle() {
  const { renderMode, setRenderMode } = useAnalysisStore()
  const t = useTranslations("analysis")

  return (
    <button
      type="button"
      onClick={() => setRenderMode(renderMode === "wireframe" ? "solid" : "wireframe")}
      className="absolute top-2 right-2 rounded-lg px-2 py-1 text-xs hover:bg-muted"
      style={{ backgroundColor: "oklch(var(--background) / 0.7)" }}
    >
      {renderMode === "wireframe" ? t("wireframe") : t("solid")}
    </button>
  )
}

function PlaybackControls() {
  const { isPlaying, setIsPlaying, setCurrentFrame, playbackSpeed, setPlaybackSpeed } =
    useAnalysisStore()

  return (
    <div
      className="absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full px-3 py-1.5 text-xs"
      style={{ backgroundColor: "oklch(var(--background) / 0.7)" }}
    >
      <button type="button" onClick={() => setCurrentFrame(f => Math.max(0, f - 10))}>
        <ChevronLeft className="h-4 w-4" />
      </button>
      <button type="button" onClick={() => setIsPlaying(!isPlaying)}>
        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </button>
      <button type="button" onClick={() => setCurrentFrame(f => f + 10)}>
        <ChevronRight className="h-4 w-4" />
      </button>
      <select
        value={playbackSpeed}
        onChange={e => setPlaybackSpeed(Number(e.target.value))}
        className="bg-transparent text-xs outline-none"
      >
        <option value={0.5}>0.5x</option>
        <option value={1}>1x</option>
        <option value={2}>2x</option>
      </select>
    </div>
  )
}

export function ThreeJSkeletonViewer({
  poseData,
  frameMetrics,
  className = "",
}: ThreeJSkeletonViewerProps) {
  return (
    <div
      className={`relative aspect-square bg-gradient-to-br from-slate-900 to-slate-800 ${className}`}
    >
      <Canvas
        dpr={[1, 2]} // Pixel ratio for sharp rendering
        gl={{ antialias: true, alpha: true }}
        className="w-full h-full"
      >
        <Suspense fallback={<LoadingFallback />}>
          <Scene poseData={poseData} frameMetrics={frameMetrics} />
        </Suspense>
      </Canvas>

      <PlaybackControls />

      <RenderModeToggle />

      <CameraPresets />

      {/* Legend */}
      <div
        className="absolute bottom-2 left-2 rounded-lg p-2 text-xs"
        style={{
          backgroundColor: "oklch(var(--background) / 0.6)",
          color: "oklch(var(--foreground))",
        }}
      >
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <div
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "oklch(var(--score-good))" }}
            />
            <span>90-170°</span>
          </div>
          <div className="flex items-center gap-1">
            <div
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "oklch(var(--score-mid))" }}
            />
            <span>60-190°</span>
          </div>
          <div className="flex items-center gap-1">
            <div
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "oklch(var(--score-bad))" }}
            />
            <span className="text-xs">&lt;60° / &gt;190°</span>
          </div>
        </div>
      </div>
    </div>
  )
}
