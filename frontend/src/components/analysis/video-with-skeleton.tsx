"use client"

import { useRef, useEffect, useState, useCallback } from "react"
import { useAnalysisStore } from "@/stores/analysis"
import type { PhasesData, PoseData } from "@/types"
import { PhaseLabels } from "./phase-labels"
import { SkeletonCanvas } from "./skeleton-canvas"
import { Play, Pause } from "lucide-react"

interface VideoWithSkeletonProps {
  videoUrl: string
  poseData: PoseData | null
  phases: PhasesData | null
  totalFrames: number
  fps?: number
  className?: string
}

export function VideoWithSkeleton({
  videoUrl,
  poseData,
  phases,
  totalFrames,
  fps = 30,
  className = "",
}: VideoWithSkeletonProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const { currentFrame, setCurrentFrame, isPlaying, setIsPlaying, playbackSpeed } =
    useAnalysisStore()

  // Sync store currentFrame → video time
  useEffect(() => {
    const video = videoRef.current
    if (!video?.duration || Number.isNaN(video.duration)) return
    const targetTime = currentFrame / fps
    if (Math.abs(video.currentTime - targetTime) > 1 / fps) {
      video.currentTime = targetTime
    }
  }, [currentFrame, fps])

  // Sync store isPlaying → video play/pause
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (isPlaying) {
      video.play().catch(() => {})
    } else {
      video.pause()
    }
  }, [isPlaying])

  // Sync store playbackSpeed → video playbackRate
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.playbackRate = playbackSpeed
  }, [playbackSpeed])

  const handleTimeUpdate = () => {
    if (!videoRef.current) return
    const video = videoRef.current
    const frame = Math.floor((video.currentTime / video.duration) * totalFrames)
    setCurrentFrame(frame)
  }

  const [showControls, setShowControls] = useState(true)
  const hideTimeout = useRef<NodeJS.Timeout | null>(null)

  const revealControls = useCallback(() => {
    setShowControls(true)
    if (hideTimeout.current) clearTimeout(hideTimeout.current)
    hideTimeout.current = setTimeout(() => setShowControls(false), 2000)
  }, [])

  const handleTogglePlay = useCallback(() => {
    setIsPlaying(!isPlaying)
    revealControls()
  }, [isPlaying, setIsPlaying, revealControls])

  useEffect(() => {
    return () => {
      if (hideTimeout.current) clearTimeout(hideTimeout.current)
    }
  }, [])

  if (!poseData) {
    // Fallback: show video without skeleton
    return (
      <div
        className={`relative ${className}`}
        style={{ backgroundColor: "oklch(var(--background))" }}
      >
        {/* biome-ignore lint/a11y/useMediaCaption: Skating analysis video has no captions */}
        <video
          ref={videoRef}
          src={videoUrl}
          className="w-full"
          controls
          onTimeUpdate={handleTimeUpdate}
        />
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={`relative aspect-video ${className}`}
      style={{ backgroundColor: "oklch(var(--background))" }}
    >
      {/* biome-ignore lint/a11y/useMediaCaption: Skating analysis video has no captions */}
      <video
        ref={videoRef}
        src={videoUrl}
        className="w-full h-full object-contain"
        onTimeUpdate={handleTimeUpdate}
      />
      <SkeletonCanvas poseData={poseData} currentFrame={currentFrame} width={1920} height={1080} />
      {phases && <PhaseLabels phases={phases} currentFrame={totalFrames} width={1920} />}
      {poseData && (
        <div
          className={`absolute inset-0 flex items-center justify-center transition-opacity duration-300 ${showControls ? "opacity-100" : "opacity-0"}`}
          onClick={handleTogglePlay}
          onMouseMove={revealControls}
        >
          <button
            type="button"
            className="rounded-full bg-black/50 p-4 text-white hover:bg-black/70"
          >
            {isPlaying ? <Pause className="h-8 w-8" /> : <Play className="h-8 w-8" />}
          </button>
        </div>
      )}
    </div>
  )
}
