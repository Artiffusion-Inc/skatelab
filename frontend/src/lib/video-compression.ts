/**
 * Frontend video compression — reduces upload size 6-10x.
 *
 * Primary: WebCodecs API via mediabunny Conversion (Chrome 94+, Edge 94+, Firefox 130+, Safari 16.4+)
 * Fallback: @ffmpeg/ffmpeg WASM (Firefox Android, runtime failures)
 *
 * Output: H.264 (avc), max 1280px, 30fps, 2 Mbps, yuv420p, no audio.
 *
 * NOTE: Use @ffmpeg/core (single-thread) only. @ffmpeg/core-mt hangs on
 * Safari/Chromium with -vf scale. No SharedArrayBuffer headers needed.
 * GPL-2.0-or-later license applies to @ffmpeg/core (includes libx264).
 */

export interface CompressOptions {
  maxWidth?: number
  maxHeight?: number
  fps?: number
  bitrate?: number
  onProgress?: (percent: number) => void
}

export interface CompressResult {
  blob: Blob
  originalSize: number
  compressedSize: number
}

const DEFAULT_OPTIONS: Required<CompressOptions> = {
  maxWidth: 1280,
  maxHeight: 720,
  fps: 30,
  bitrate: 2_000_000,
  onProgress: () => {},
}

/** Skip files under 10 MB — already small enough. */
export function shouldCompress(file: File): boolean {
  if (file.size < 10 * 1024 * 1024) return false
  return true
}

/** Check WebCodecs API availability. */
export function isWebCodecsSupported(): boolean {
  return typeof VideoDecoder !== "undefined" && typeof VideoEncoder !== "undefined"
}

/** Get video dimensions and duration via <video> element. */
function getVideoMetadata(
  file: File,
): Promise<{ width: number; height: number; duration: number }> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video")
    video.preload = "metadata"
    video.onloadedmetadata = () => {
      const meta = {
        width: video.videoWidth,
        height: video.videoHeight,
        duration: video.duration || 0,
      }
      URL.revokeObjectURL(video.src)
      resolve(meta)
    }
    video.onerror = () => {
      URL.revokeObjectURL(video.src)
      reject(new Error("Failed to load video metadata"))
    }
    video.src = URL.createObjectURL(file)
  })
}

/**
 * Compress video using WebCodecs API via mediabunny Conversion.
 * Handles demux → decode → resize → re-encode → mux automatically.
 * Falls back to HEVC/VP9 if AVC not supported by browser.
 */
export async function compressVideoWebCodecs(
  file: File,
  opts: CompressOptions = {},
): Promise<CompressResult> {
  const options = { ...DEFAULT_OPTIONS, ...opts }

  const {
    Conversion,
    Input,
    Output,
    BlobSource,
    BufferTarget,
    Mp4OutputFormat,
    Mp4InputFormat,
    getFirstEncodableVideoCodec,
    VIDEO_CODECS,
  } = await import("mediabunny")

  const { width: srcW, height: srcH } = await getVideoMetadata(file)

  // 4K guard — WebCodecs may OOM on very large inputs
  if (srcW > 3840 || srcH > 2160) {
    throw new Error(
      "Video resolution too high for browser compression. Please use a lower-resolution recording.",
    )
  }

  // Calculate output dimensions (even, fit within maxWidth×maxHeight)
  const scale = Math.min(options.maxWidth / srcW, options.maxHeight / srcH, 1)
  const outW = Math.round((srcW * scale) / 2) * 2
  const outH = Math.round((srcH * scale) / 2) * 2

  // Pick best available codec — prefer AVC (H.264)
  const codec = await getFirstEncodableVideoCodec([...VIDEO_CODECS], {
    width: outW,
    height: outH,
    bitrate: options.bitrate,
  })

  if (!codec) {
    throw new Error("No supported video codec found for WebCodecs encoding")
  }

  const target = new BufferTarget()

  const input = new Input({
    source: new BlobSource(file),
    formats: [new Mp4InputFormat()],
  })

  const output = new Output({
    format: new Mp4OutputFormat(),
    target,
  })

  const conversion = await Conversion.init({
    input,
    output,
    tracks: "primary",
    video: {
      codec,
      width: outW,
      height: outH,
      fit: "contain",
      frameRate: options.fps,
      bitrate: options.bitrate,
    },
    audio: {
      discard: true,
    },
  })

  if (!conversion.isValid) {
    const reasons = conversion.discardedTracks.map(t => t.reason).join(", ")
    throw new Error(`Conversion invalid — discarded tracks: ${reasons}`)
  }

  conversion.onProgress = (progress: number) => {
    options.onProgress(Math.min(Math.round(progress * 100), 99))
  }

  await conversion.execute()

  const buffer = target.buffer
  if (!buffer) {
    throw new Error("Conversion produced no output")
  }

  const blob = new Blob([buffer], { type: "video/mp4" })
  options.onProgress(100)

  return {
    blob,
    originalSize: file.size,
    compressedSize: blob.size,
  }
}

/** Extract video duration in seconds for progress tracking. */
function getVideoDuration(file: File): Promise<number> {
  return new Promise(resolve => {
    const video = document.createElement("video")
    video.preload = "metadata"
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(video.src)
      resolve(video.duration || 0)
    }
    video.onerror = () => resolve(0)
    video.src = URL.createObjectURL(file)
  })
}

/**
 * Compress video using ffmpeg.wasm (fallback).
 * Loads ~30.7 MB WASM on first call (~8-12 MB compressed transfer).
 * Uses single-thread @ffmpeg/core only — multi-thread hangs with -vf scale.
 * Cross-origin loads via toBlobURL to avoid Worker security restrictions.
 */
export async function compressVideoFFmpeg(
  file: File,
  opts: CompressOptions = {},
): Promise<CompressResult> {
  const options = { ...DEFAULT_OPTIONS, ...opts }

  const { FFmpeg } = await import("@ffmpeg/ffmpeg")
  const { fetchFile, toBlobURL } = await import("@ffmpeg/util")

  const ffmpeg = new FFmpeg()
  const baseURL = "https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd"
  await ffmpeg.load({
    coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
    wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
    workerURL: await toBlobURL(`${baseURL}/ffmpeg-core.worker.js`, "text/javascript"),
  })

  await ffmpeg.writeFile("input.mp4", await fetchFile(file))

  // Time-based progress — ratio is inaccurate with resampling
  const inputDuration = await getVideoDuration(file)
  ffmpeg.on("progress", ({ time }) => {
    if (inputDuration > 0) {
      const percent = Math.min(Math.round((time / 1e6 / inputDuration) * 100), 99)
      options.onProgress(percent)
    }
  })

  await ffmpeg.exec([
    "-i",
    "input.mp4",
    "-vf",
    `scale=${options.maxWidth}:-2`,
    "-r",
    String(options.fps),
    "-c:v",
    "libx264",
    "-crf",
    "28",
    "-an",
    "-pix_fmt",
    "yuv420p",
    "output.mp4",
  ])

  const data = (await ffmpeg.readFile("output.mp4")) as Uint8Array
  const blob = new Blob([new Uint8Array(data)], { type: "video/mp4" })

  return {
    blob,
    originalSize: file.size,
    compressedSize: blob.size,
  }
}

/**
 * Auto-select best compression method with runtime fallback.
 * Tries WebCodecs first; on failure, falls back to ffmpeg.wasm.
 */
export async function compressVideo(
  file: File,
  opts: CompressOptions = {},
): Promise<CompressResult> {
  if (isWebCodecsSupported()) {
    try {
      return await compressVideoWebCodecs(file, opts)
    } catch (e) {
      console.warn("WebCodecs compression failed, falling back to ffmpeg.wasm:", e)
    }
  }
  return compressVideoFFmpeg(file, opts)
}
