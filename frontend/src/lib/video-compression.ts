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

const SKIP_THRESHOLD = 10 * 1024 * 1024 // 10 MB — files below skip compression
export const COMPRESSION_TIMEOUT_MS = 60_000 // 60s — skip compression on timeout

/** Skip files under threshold — already small enough. */
export function shouldCompress(file: File): boolean {
  return file.size >= SKIP_THRESHOLD
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
    video.preload = "auto"
    const cleanup = () => URL.revokeObjectURL(video.src)

    const onError = () => {
      cleanup()
      reject(new Error("Failed to load video metadata"))
    }

    // loadedmetadata fires first but videoWidth may be 0 for HEVC/unsupported codecs.
    // Wait for loadeddata (first frame decoded) for reliable dimensions.
    video.onloadeddata = () => {
      const meta = {
        width: video.videoWidth,
        height: video.videoHeight,
        duration: video.duration || 0,
      }
      cleanup()
      resolve(meta)
    }

    // Fallback: some browsers fire loadedmetadata with dimensions but skip loadeddata
    video.onloadedmetadata = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        const meta = {
          width: video.videoWidth,
          height: video.videoHeight,
          duration: video.duration || 0,
        }
        cleanup()
        resolve(meta)
      }
      // else: wait for loadeddata
    }

    video.onerror = onError
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
    QuickTimeInputFormat,
    getFirstEncodableVideoCodec,
    VIDEO_CODECS,
  } = await import("mediabunny")

  let { width: srcW, height: srcH } = await getVideoMetadata(file)

  // HEVC/MOV fallback: <video> may report 0x0 for unsupported codecs.
  // Parse container headers via mediabunny Input to get dimensions.
  if (srcW === 0 || srcH === 0) {
    const probeInput = new Input({
      source: new BlobSource(file),
      formats: [new Mp4InputFormat(), new QuickTimeInputFormat()],
    })
    const track = await probeInput.getPrimaryVideoTrack()
    if (track) {
      srcW = track.codedWidth || (await track.getCodedWidth()) || 0
      srcH = track.codedHeight || (await track.getCodedHeight()) || 0
    }
    if (srcW === 0 || srcH === 0) {
      throw new Error(
        "Cannot determine video dimensions. The codec may not be supported by your browser.",
      )
    }
  }

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
    formats: [new Mp4InputFormat(), new QuickTimeInputFormat()],
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

  // #824: enforce the documented 60s timeout on WebCodecs path too.
  await Promise.race([
    conversion.execute(),
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error(`Compression timed out after ${COMPRESSION_TIMEOUT_MS}ms`)),
        COMPRESSION_TIMEOUT_MS,
      ),
    ),
  ])

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

/** Extract video duration in seconds for ffmpeg.wasm progress tracking. */
function getVideoDuration(file: File): Promise<number> {
  return getVideoMetadata(file)
    .then(m => m.duration)
    .catch(() => 0)
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

  // #823: match WebCodecs upscale policy — scale = min(max/W, max/H, 1),
  // capped at 1 so small videos are NOT upscaled. Was: `scale=${maxWidth}:-2`
  // which always scaled width to maxWidth (1280), inflating 640×480 → 1280×960.
  let scaleFilter = `scale='min(${options.maxWidth},iw)':-2`
  try {
    const meta = await getVideoMetadata(file)
    if (meta.width > 0 && meta.height > 0) {
      const scale = Math.min(options.maxWidth / meta.width, options.maxHeight / meta.height, 1)
      const outW = Math.round((meta.width * scale) / 2) * 2
      const outH = Math.round((meta.height * scale) / 2) * 2
      scaleFilter = `scale=${outW}:${outH}`
    }
  } catch {
    // metadata unavailable — keep the conservative min() fallback above
  }

  const execPromise = ffmpeg.exec([
    "-i",
    "input.mp4",
    "-vf",
    scaleFilter,
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

  // #824: enforce the documented 60s timeout. Was: COMPRESSION_TIMEOUT_MS
  // exported but never referenced — hung compression blocked indefinitely.
  await Promise.race([
    execPromise,
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error(`Compression timed out after ${COMPRESSION_TIMEOUT_MS}ms`)),
        COMPRESSION_TIMEOUT_MS,
      ),
    ),
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
