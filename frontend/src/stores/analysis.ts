import { create } from "zustand"

export interface AnalysisState {
  currentFrame: number
  isPlaying: boolean
  playbackSpeed: number
  selectedJoint: number | null
  hoveredJoint: number | null
  cameraPreset: "front" | "side" | "top"
  renderMode: "wireframe" | "solid"

  // Actions
  setCurrentFrame: (frame: number | ((prev: number) => number)) => void
  setIsPlaying: (playing: boolean) => void
  setPlaybackSpeed: (speed: number) => void
  setSelectedJoint: (joint: number | null) => void
  setHoveredJoint: (joint: number | null) => void
  setCameraPreset: (preset: "front" | "side" | "top") => void
  setRenderMode: (mode: "wireframe" | "solid") => void
  reset: () => void
}

export const useAnalysisStore = create<AnalysisState>(set => ({
  currentFrame: 0,
  isPlaying: false,
  playbackSpeed: 1.0,
  selectedJoint: null,
  hoveredJoint: null,
  cameraPreset: "front",
  renderMode: "wireframe",

  setCurrentFrame: (frame: number | ((prev: number) => number)) =>
    set((state: AnalysisState) => ({
      currentFrame: typeof frame === "function" ? frame(state.currentFrame) : frame,
    })),
  setIsPlaying: playing => set({ isPlaying: playing }),
  setPlaybackSpeed: speed => set({ playbackSpeed: speed }),
  setSelectedJoint: joint => set({ selectedJoint: joint }),
  setHoveredJoint: joint => set({ hoveredJoint: joint }),
  setCameraPreset: preset => set({ cameraPreset: preset }),
  setRenderMode: mode => set({ renderMode: mode }),

  reset: () =>
    set({
      currentFrame: 0,
      isPlaying: false,
      playbackSpeed: 1.0,
      selectedJoint: null,
      hoveredJoint: null,
      cameraPreset: "front",
      renderMode: "wireframe",
    }),
}))
