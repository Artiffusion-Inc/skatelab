# GPU Cold Start + Video Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate R2 model download from GPU worker cold start, compress video on frontend before upload.

**Architecture:** (1) Frontend compresses video via WebCodecs API (Chrome 94+, Edge 94+, Firefox 130+, Safari 16.4+) with ffmpeg.wasm fallback (Firefox Android, runtime failures) before ChunkedUploader sends it to R2. Compression uses `mediabunny` for demux+mux pipeline. (2) Docker image embeds ONNX models at build time via Docker secrets + cache mounts (no cache invalidation, no URL in image metadata). (3) GPU server removes `_download_models_from_r2()`, simplifies `_background_init()`.

**Tech Stack:** WebCodecs API, mediabunny (demux+mux), @ffmpeg/ffmpeg (WASM, single-thread only), H.264/AVC (High Profile + Baseline fallback), Python boto3 (pre-signed URL script), podman multi-stage build with --mount=type=secret+cache, FastAPI, pytest, vitest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/lib/video-compression.ts` | WebCodecs (mediabunny) + ffmpeg.wasm compression logic |
| Create | `frontend/src/lib/video-compression.worker.ts` | Web Worker for off-main-thread compression |
| Modify | `frontend/src/components/upload/drop-zone.tsx` | Update MAX_SIZE 500→50 MB |
| Modify | `frontend/src/app/(app)/upload/page.tsx` | Add compression step between file pick and upload |
| Modify | `frontend/messages/ru.json` | Add compression i18n keys (ru) |
| Modify | `frontend/messages/en.json` | Add compression i18n keys (en) |
| Modify | `ml/gpu_server/Containerfile` | Add model_fetch stage, remove R2 env comment |
| Modify | `ml/gpu_server/server.py` | Remove `_download_models_from_r2()`, `_R2_MODELS`, simplify `_background_init()` |
| Create | `ml/scripts/generate_model_presigned_urls.py` | CI script to generate pre-signed R2 URLs for build |
| Modify | `Taskfile.yml` | Update `vastai-build` task with pre-signed URL flow |

---

## Wave 1: GPU Server Cleanup (Section 2+3 of spec)

Independent of frontend. Can be tested locally with mock model files.

### Task 1: Simplify `_background_init()` in server.py

**Files:**

- Modify: `ml/gpu_server/server.py:61-136`

- [ ] **Step 1: Write the failing test**

Create `ml/tests/gpu_server/test_background_init.py`:

```python
"""Test _background_init works without R2 model download."""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def mock_model_paths(tmp_path):
    """Create fake model files and patch paths."""
    mog = tmp_path / "moganet" / "moganet_b_ap2d_384x288.onnx"
    yolo = tmp_path / "yolov8n.onnx"
    mog.parent.mkdir(parents=True, exist_ok=True)
    mog.write_bytes(b"fake-moganet")
    yolo.write_bytes(b"fake-yolo")
    return mog, yolo


@pytest.mark.asyncio
async def test_background_init_succeeds_when_models_exist(mock_model_paths):
    mog, yolo = mock_model_paths
    import gpu_server.server as srv

    with (
        patch.object(srv, "MOGANET_MODEL_PATH", mog),
        patch.object(srv, "YOLO_MODEL_PATH", yolo),
        patch("src.device.DeviceConfig") as MockDC,
    ):
        MockDC.default.return_value.is_cuda = False
        await srv._background_init()
        assert srv._models_ready is True


@pytest.mark.asyncio
async def test_background_init_fails_when_models_missing(tmp_path):
    missing = tmp_path / "nonexistent.onnx"
    import gpu_server.server as srv

    with (
        patch.object(srv, "MOGANET_MODEL_PATH", missing),
        patch.object(srv, "YOLO_MODEL_PATH", tmp_path / "also_missing.onnx"),
    ):
        await srv._background_init()
        assert srv._models_ready is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ml && uv run python -m pytest tests/gpu_server/test_background_init.py -v`
Expected: FAIL — `_download_models_from_r2()` still called, `_R2_MODELS` still referenced

- [ ] **Step 3: Write minimal implementation**

In `ml/gpu_server/server.py`, replace lines 60-136 (from `_R2_MODELS` through `_background_init()`) with:

```python
_models_ready = False


async def _background_init():
    """Verify models exist + warmup CUDA — runs after server is accepting requests."""
    global _models_ready  # noqa: PLW0603
    try:
        if not MOGANET_MODEL_PATH.exists():
            raise OSError(f"Model not found: {MOGANET_MODEL_PATH}")
        if not YOLO_MODEL_PATH.exists():
            raise OSError(f"Model not found: {YOLO_MODEL_PATH}")

        from src.device import DeviceConfig

        cfg = DeviceConfig.default()
        if cfg.is_cuda:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 2
            logger.info("GPU warmup: CUDA initialized")

        _models_ready = True
        logger.info("Background init complete — models ready")
    except (OSError, ValueError, RuntimeError):
        logger.exception("Background init failed")
        _models_ready = False
```

Delete:
- `_R2_MODELS` list (lines 61-64)
- `_download_models_from_r2()` function (lines 70-108)

Keep unchanged: `MOGANET_MODEL_PATH`, `YOLO_MODEL_PATH`, `_async_session`, `_models_ready`, `_s3()`, `_s3_download()`, `_s3_upload()`, all endpoints.

Also change `/ready` endpoint detail text: `"models downloading"` → `"models initializing"` (server.py line ~156).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ml && uv run python -m pytest tests/gpu_server/test_background_init.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/gpu_server/server.py ml/tests/gpu_server/test_background_init.py
git commit -m "refactor(gpu_server): remove R2 model download, simplify _background_init()"
```

---

### Task 2: Update Containerfile with model_fetch stage

**Files:**

- Modify: `ml/gpu_server/Containerfile`

- [ ] **Step 1: Add model_fetch stage with Docker secrets + cache mounts**

After the `builder` stage (line 55), add a new stage:

```dockerfile
# Stage 2: model download (new stage)
# Uses Docker secrets for pre-signed URLs (not in image metadata)
# Uses cache mount to persist model files across builds
FROM docker.io/python:3.11-slim AS model_fetch

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Secret files containing pre-signed URLs (one URL per file)
# Cache mount persists downloads across builds — no re-download on URL rotation
RUN --mount=type=secret,id=moganet_url \
    --mount=type=secret,id=yolo_url \
    --mount=type=cache,target=/model-cache \
    mkdir -p /models/moganet && \
    MOGANET_URL=$(cat /run/secrets/moganet_url) && \
    if [ ! -f /model-cache/moganet_b_ap2d_384x288.onnx ]; then \
      curl -sS --fail -o /model-cache/moganet_b_ap2d_384x288.onnx "$MOGANET_URL"; \
    fi && \
    cp /model-cache/moganet_b_ap2d_384x288.onnx /models/moganet/ && \
    YOLO_URL=$(cat /run/secrets/yolo_url) && \
    if [ ! -f /model-cache/yolov8n.onnx ]; then \
      curl -sS --fail -o /model-cache/yolov8n.onnx "$YOLO_URL"; \
    fi && \
    cp /model-cache/yolov8n.onnx /models/
```

In the runtime stage, replace the `mkdir` line (line 83):

```dockerfile
# ONNX models copied from model_fetch stage
RUN mkdir -p /app/data/models && chown appuser:appuser /app /app/data /app/data/models
COPY --from=model_fetch --chown=appuser:appuser /models/ /app/data/models/
```

Note: `--mount=type=secret` keeps URLs out of image metadata. `--mount=type=cache` persists 300 MB models across builds — no re-download when URLs rotate. YOLO model goes to `/models/yolov8n.onnx` (flat, matching `server.py` path `data/models/yolov8n.onnx`).

- [ ] **Step 2: Verify Containerfile syntax**

Run: `podman build --check -f ml/gpu_server/Containerfile .`
Expected: syntax OK (or manual review — `podman build --check` may not exist; visual inspection sufficient)

- [ ] **Step 3: Commit**

```bash
git add ml/gpu_server/Containerfile
git commit -m "feat(gpu_server): add model_fetch stage to Containerfile for build-time model embedding"
```

---

### Task 3: Create pre-signed URL generator script

**Files:**

- Create: `ml/scripts/generate_model_presigned_urls.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Generate pre-signed R2 URLs for ONNX models.

Used at Docker build time to embed models into the image.
URLs expire after 1 hour — generate immediately before build.

Usage:
    uv run python scripts/generate_model_presigned_urls.py --output /tmp/model_urls.json

Requires env vars: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import boto3


MODELS = {
    "moganet": "models/moganet/moganet_b_ap2d_384x288.onnx",
    "yolo": "models/yolov8n.onnx",
}

DEFAULT_EXPIRES = 3600  # 1 hour


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pre-signed R2 URLs for model download")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--expires", type=int, default=DEFAULT_EXPIRES, help="URL expiry in seconds")
    args = parser.parse_args()

    endpoint = os.environ.get("R2_ENDPOINT_URL", "")
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    bucket = os.environ.get("R2_BUCKET", "")

    missing = [k for k, v in {
        "R2_ENDPOINT_URL": endpoint,
        "R2_ACCESS_KEY_ID": access_key,
        "R2_SECRET_ACCESS_KEY": secret,
        "R2_BUCKET": bucket,
    }.items() if not v]

    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name="auto",
    )

    urls: dict[str, str] = {}
    for name, key in MODELS.items():
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=args.expires,
        )
        urls[name] = url
        print(f"  {name}: {key} → URL generated (expires in {args.expires}s)")

    with open(args.output, "w") as f:
        json.dump(urls, f, indent=2)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script runs (dry test with --help)**

Run: `cd ml && uv run python scripts/generate_model_presigned_urls.py --help`
Expected: prints usage text, exits 0

- [ ] **Step 3: Commit**

```bash
git add ml/scripts/generate_model_presigned_urls.py
git commit -m "feat(ml): add pre-signed R2 URL generator for Docker build"
```

---

### Task 4: Update Taskfile.yml vastai-build task

**Files:**

- Modify: `Taskfile.yml:124-136`

- [ ] **Step 1: Replace vastai-build, vastai-deploy tasks**

Replace lines 124-136:

```yaml
  # Vast.ai Serverless tasks
  vastai-presign:
    desc: Generate pre-signed R2 URLs for model embedding (requires R2 env vars)
    dir: ml
    cmds:
      - uv run python scripts/generate_model_presigned_urls.py --output /tmp/model_urls.json
      # Write URLs to individual files for Docker secrets
      - jq -r .moganet /tmp/model_urls.json > /tmp/moganet_url.txt
      - jq -r .yolo /tmp/model_urls.json > /tmp/yolo_url.txt

  vastai-build:
    desc: Build GPU worker image with embedded models (run vastai-presign first)
    cmds:
      - podman build
          --secret id=moganet_url,src=/tmp/moganet_url.txt
          --secret id=yolo_url,src=/tmp/yolo_url.txt
          -f ml/gpu_server/Containerfile
          -t ghcr.io/Artiffusion-Inc/skatelab-worker:latest
          .

  vastai-push:
    desc: Push GPU worker image to ghcr.io
    cmd: podman push ghcr.io/Artiffusion-Inc/skatelab-worker:latest

  vastai-deploy:
    desc: Generate URLs, build and push GPU worker image
    cmds:
      - task: vastai-presign
      - task: vastai-build
      - task: vastai-push
```

- [ ] **Step 2: Verify task listing**

Run: `go-task --list | grep vastai`
Expected: shows vastai-presign, vastai-build, vastai-push, vastai-deploy

- [ ] **Step 3: Commit**

```bash
git add Taskfile.yml
git commit -m "feat(ci): update vastai-build with pre-signed URL model embedding"
```

---

## Wave 2: Frontend Video Compression (Section 1 of spec)

### Task 5: Create video compression module

**Files:**

- Create: `frontend/src/lib/video-compression.ts`

- [ ] **Step 1: Write compression module**

```typescript
/**
 * Frontend video compression — reduces upload size 6-10x.
 *
 * Primary: WebCodecs API (Chrome 94+, Edge 94+, Firefox 130+, Safari 16.4+)
 * Fallback: @ffmpeg/ffmpeg WASM (Firefox Android, runtime failures)
 *
 * Output: H.264, max 1280px, 30fps, CRF ~28, yuv420p, no audio.
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

/** Check if file should be compressed (skip small or already-optimal videos). */
export function shouldCompress(file: File): boolean {
  // Skip files under 10 MB — already small enough
  if (file.size < 10 * 1024 * 1024) return false
  return true
}

export function isWebCodecsSupported(): boolean {
  return typeof VideoDecoder !== "undefined" && typeof VideoEncoder !== "undefined"
}

/**
 * Compress video using WebCodecs API.
 * Demux → decode → resize → re-encode → mux into MP4 via mediabunny.
 * Falls back to Baseline profile if High Profile not supported.
 */
export async function compressVideoWebCodecs(
  file: File,
  opts: CompressOptions = {},
): Promise<CompressResult> {
  const options = { ...DEFAULT_OPTIONS, ...opts }

  // Dynamic import — mediabunny handles demux + mux
  const { Muxer, ArrayBufferTarget, Demuxer, FileDataSource } = await import("mediabunny")

  // Determine output dimensions from video metadata
  const video = document.createElement("video")
  video.src = URL.createObjectURL(file)
  await new Promise((resolve, reject) => {
    video.onloadedmetadata = resolve
    video.onerror = reject
  })
  const srcW = video.videoWidth
  const srcH = video.videoHeight
  URL.revokeObjectURL(video.src)

  // Check 4K guard — WebCodecs may OOM on very large inputs
  if (srcW > 3840 || srcH > 2160) {
    throw new Error("Video resolution too high for browser compression. Please use a lower-resolution recording.")
  }

  const scale = Math.min(options.maxWidth / srcW, options.maxHeight / srcH, 1)
  const outW = Math.round(srcW * scale / 2) * 2  // even dimensions for H.264
  const outH = Math.round(srcH * scale / 2) * 2

  // Check codec support — fall back to Baseline if High not supported
  const preferredCodec = "avc1.64001F"  // High Profile, Level 3.1
  const fallbackCodec = "avc1.42001E"   // Baseline Profile, Level 3

  const codecSupport = await VideoEncoder.isConfigSupported({
    codec: preferredCodec,
    width: outW,
    height: outH,
    bitrate: options.bitrate,
    framerate: options.fps,
  })
  const codec = codecSupport.supported ? preferredCodec : fallbackCodec

  // Muxer for output MP4
  const chunks: Uint8Array[] = []
  const muxer = new Muxer({
    target: new ArrayBufferTarget(),
    video: {
      codec: "avc",
      width: outW,
      height: outH,
    },
    fastStart: "in-memory",
  })

  // Encoder
  const encoder = new VideoEncoder({
    output: (chunk, meta) => {
      muxer.addVideoChunk(chunk, meta)
      chunks.push(new Uint8Array(chunk.byteLength))
    },
    error: (e) => { throw e },
  })

  encoder.configure({
    codec,
    width: outW,
    height: outH,
    bitrate: options.bitrate,
    framerate: options.fps,
    latencyMode: "quality",
  })

  // Demux + decode input
  const demuxer = new Demuxer(new FileDataSource(file))
  const videoTrack = demuxer.videoTracks[0]
  if (!videoTrack) throw new Error("No video track found")

  const { codec: inputCodec, trackNumber, description } = await demuxer.initialize(videoTrack)

  let frameCount = 0
  const totalFrames = Math.ceil(demuxer.duration * options.fps) || 1

  const decoder = new VideoDecoder({
    output: (frame) => {
      // Assign minimum duration for very short videos (duration=0 frames)
      const duration = frame.duration || (1_000_000 / options.fps)
      encoder.encode(frame, { keyFrame: frameCount % 30 === 0 })
      frame.close()
      frameCount++
      options.onProgress(Math.min(Math.round((frameCount / totalFrames) * 100), 99))
    },
    error: (e) => { throw e },
  })

  decoder.configure({ codec: inputCodec, description })

  // Feed samples from demuxer to decoder
  while (true) {
    const sample = await demuxer.getNextSample(trackNumber)
    if (!sample) break
    const chunk = new EncodedVideoChunk({
      type: sample.isSync ? "key" : "delta",
      timestamp: sample.dts,
      duration: sample.duration,
      data: sample.data,
    })
    decoder.decode(chunk)
  }

  await decoder.flush()
  await encoder.flush()
  encoder.close()

  muxer.finalize()
  const buffer = (muxer.target as InstanceType<typeof ArrayBufferTarget>).buffer
  const blob = new Blob([buffer], { type: "video/mp4" })

  options.onProgress(100)

  return {
    blob,
    originalSize: file.size,
    compressedSize: blob.size,
  }
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

  // Use time-based progress — ratio-based progress is inaccurate with resampling
  const inputDuration = await getVideoDuration(file)
  ffmpeg.on("progress", ({ time }) => {
    if (inputDuration > 0) {
      const percent = Math.min(Math.round((time / 1e6 / inputDuration) * 100), 99)
      options.onProgress(percent)
    }
  })

  await ffmpeg.exec([
    "-i", "input.mp4",
    "-vf", `scale=${options.maxWidth}:-2`,
    "-r", String(options.fps),
    "-c:v", "libx264",
    "-crf", "28",
    "-an",
    "-pix_fmt", "yuv420p",
    "output.mp4",
  ])

  const data = await ffmpeg.readFile("output.mp4")
  const blob = new Blob([data], { type: "video/mp4" })

  return {
    blob,
    originalSize: file.size,
    compressedSize: blob.size,
  }
}

/** Extract video duration in seconds for progress tracking. */
function getVideoDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
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
```

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && bun add mediabunny @ffmpeg/ffmpeg @ffmpeg/util`

Note: `mediabunny` replaces both `mp4-muxer` and the fictional `mp4-demuxer`. `@ffmpeg/ffmpeg` and `@ffmpeg/util` are the WASM fallback. **Use `@ffmpeg/core` (single-thread) only — do NOT use `@ffmpeg/core-mt`.**

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no errors in `video-compression.ts`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/video-compression.ts frontend/package.json frontend/bun.lock
git commit -m "feat(frontend): add video compression module (WebCodecs via mediabunny + ffmpeg.wasm fallback)"
```

---

### Task 6: Create Web Worker for off-main-thread compression

**Files:**

- Create: `frontend/src/lib/video-compression.worker.ts`

- [ ] **Step 1: Write the Web Worker**

```typescript
/**
 * Web Worker for video compression — keeps UI thread responsive.
 * Posts progress updates and the compressed Blob back to main thread.
 */
import { compressVideo, type CompressOptions, type CompressResult } from "./video-compression"

interface WorkerMessage {
  type: "compress"
  file: File
  options: CompressOptions
}

interface WorkerResponse {
  type: "progress" | "result" | "error"
  percent?: number
  result?: { originalSize: number; compressedSize: number }
  error?: string
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  if (e.data.type !== "compress") return

  const { file, options } = e.data

  const respond = (msg: WorkerResponse) => self.postMessage(msg)

  try {
    const result = await compressVideo(file, {
      ...options,
      onProgress: (percent) => respond({ type: "progress", percent }),
    })

    // Transfer the blob — can't be structured-cloned efficiently
    respond({
      type: "result",
      result: {
        originalSize: result.originalSize,
        compressedSize: result.compressedSize,
      },
    })

    // Send blob separately as transferable
    self.postMessage({ type: "blob", blob: result.blob } as { type: "blob"; blob: Blob })
  } catch (err) {
    respond({ type: "error", error: String(err) })
  }
}
```

- [ ] **Step 2: Create helper hook to use the worker**

Create `frontend/src/lib/use-video-compression.ts`:

```typescript
"use client"

import { useRef, useCallback, useState } from "react"
import type { CompressResult } from "./video-compression"

export type CompressionState =
  | { status: "idle" }
  | { status: "compressing"; percent: number }
  | { status: "done"; result: CompressResult }
  | { status: "error"; error: string }

export function useVideoCompression() {
  const workerRef = useRef<Worker | null>(null)
  const [state, setState] = useState<CompressionState>({ status: "idle" })

  const compress = useCallback((file: File): Promise<CompressResult> => {
    return new Promise((resolve, reject) => {
      setState({ status: "compressing", percent: 0 })

      const worker = new Worker(
        new URL("./video-compression.worker.ts", import.meta.url),
      )
      workerRef.current = worker

      let blob: Blob | null = null
      let meta: { originalSize: number; compressedSize: number } | null = null

      worker.onmessage = (e) => {
        const data = e.data
        if (data.type === "progress") {
          setState({ status: "compressing", percent: data.percent })
        } else if (data.type === "result") {
          meta = data.result
        } else if (data.type === "blob") {
          blob = data.blob
          if (meta) {
            const result: CompressResult = {
              blob,
              originalSize: meta.originalSize,
              compressedSize: meta.compressedSize,
            }
            setState({ status: "done", result })
            worker.terminate()
            resolve(result)
          }
        } else if (data.type === "error") {
          setState({ status: "error", error: data.error })
          worker.terminate()
          reject(new Error(data.error))
        }
      }

      worker.onerror = (err) => {
        setState({ status: "error", error: String(err) })
        worker.terminate()
        reject(err)
      }

      worker.postMessage({
        type: "compress",
        file,
        options: { maxWidth: 1280, maxHeight: 720, fps: 30, bitrate: 2_000_000 },
      })
    })
  }, [])

  const abort = useCallback(() => {
    workerRef.current?.terminate()
    workerRef.current = null
    setState({ status: "idle" })
  }, [])

  return { state, compress, abort }
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/video-compression.worker.ts frontend/src/lib/use-video-compression.ts
git commit -m "feat(frontend): add Web Worker + hook for off-main-thread video compression"
```

---

### Task 7: Add i18n keys for compression

**Files:**

- Modify: `frontend/messages/ru.json`
- Modify: `frontend/messages/en.json`

- [ ] **Step 1: Add keys to ru.json**

In the `"upload"` section, add after `"remove": "Удалить"`:

```json
    "compressing": "Сжатие видео... {percent}%",
    "compressionDone": "Сжато: {original} → {compressed}",
    "compressionError": "Ошибка сжатия видео",
    "compressionSkip": "Пропустить сжатие"
```

Update existing keys:
- `"maxSize": "до 500 МБ"` → `"maxSize": "до 50 МБ"`
- `"fileTooLarge": "Файл слишком большой (макс. 500 МБ)"` → `"fileTooLarge": "Файл слишком большой (макс. 50 МБ)"`

- [ ] **Step 2: Add keys to en.json**

In the `"upload"` section, add after `"remove": "Remove"`:

```json
    "compressing": "Compressing video... {percent}%",
    "compressionDone": "Compressed: {original} → {compressed}",
    "compressionError": "Video compression error",
    "compressionSkip": "Skip compression"
```

Update existing keys:
- `"maxSize": "up to 500 MB"` → `"maxSize": "up to 50 MB"`
- `"fileTooLarge": "File too large (max 500 MB)"` → `"fileTooLarge": "File too large (max 50 MB)"`

- [ ] **Step 3: Verify i18n structure**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -5`
Expected: no type errors from i18n

- [ ] **Step 4: Commit**

```bash
git add frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(i18n): add compression keys, update max size 500→50 MB"
```

---

### Task 8: Update DropZone max size

**Files:**

- Modify: `frontend/src/components/upload/drop-zone.tsx:10`

- [ ] **Step 1: Update MAX_SIZE constant**

```typescript
const MAX_SIZE = 50 * 1024 * 1024 // 50MB (compressed)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/upload/drop-zone.tsx
git commit -m "feat(upload): reduce max upload size 500→50 MB (frontend compression)"
```

---

### Task 9: Integrate compression into upload flow

**Files:**

- Modify: `frontend/src/app/(app)/upload/page.tsx`

- [ ] **Step 1: Add compression step type and state**

Update `Step` type and add compression hook:

```typescript
"use client"

import { useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { Loader2, CheckCircle2, X } from "lucide-react"
import { toast } from "sonner"
import { useTranslations } from "@/i18n"
import { useMountEffect } from "@/lib/useMountEffect"
import { ChunkedUploader, presignUpload, uploadToPresignedUrl } from "@/lib/api/uploads"
import { useCreateSession, usePatchSession } from "@/lib/api/sessions"
import { enqueueProcess } from "@/lib/api/process"
import { parseZip, isZipFile, type ZipContents } from "@/lib/zip-parser"
import { DropZone } from "@/components/upload/drop-zone"
import { FilePreview } from "@/components/upload/file-preview"
import { useVideoCompression, type CompressionState } from "@/lib/use-video-compression"
import { shouldCompress } from "@/lib/video-compression"

type Step = "idle" | "parsing" | "picked" | "compressing" | "uploading" | "done"
```

- [ ] **Step 2: Add compression hook and compression step to handleUpload**

In the component, add the hook:

```typescript
  const { state: compressionState, compress, abort: abortCompression } = useVideoCompression()
```

Replace `handleUpload` function. Add compression phase before Phase 1 (IMU upload):
Compression includes: skip heuristic (< 10 MB), 60-second timeout, and ZIP video extraction.

```typescript
  async function handleUpload() {
    if (!file) return
    setStep("compressing")
    setProgress(0)

    try {
      // Phase 0: Compress video before upload
      // Extract video from ZIP if needed, then compress if > 10 MB
      const videoFile = zipContents?.video ?? file

      let compressedFile: File = videoFile
      if (shouldCompress(videoFile)) {
        try {
          const result = await Promise.race([
            compress(videoFile, {
              onProgress: (percent) => setProgress(percent),
            }),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error("Compression timeout")), 60_000),
            ),
          ])
          compressedFile = new File([result.blob], "compressed.mp4", { type: "video/mp4" })
          toast.success(
            t("compressionDone", {
              original: `${(result.originalSize / 1e6).toFixed(1)} MB`,
              compressed: `${(result.compressedSize / 1e6).toFixed(1)} MB`,
            }),
          )
        } catch {
          // Timeout or error — skip compression, upload original
          toast.info(t("compressionSkip"))
        }
      }

      setStep("uploading")
      setProgress(0)

      let imuLeftKey: string | null = null
      let imuRightKey: string | null = null
      let manifestKey: string | null = null

      // Phase 1: Upload IMU/manifest to R2 via presigned URLs (if ZIP)
      if (zipContents) {
        setUploadPhase(t("uploadingImu"))

        if (zipContents.imuLeft) {
          imuLeftKey = await uploadToR2(
            new Blob([new Uint8Array(zipContents.imuLeft)]),
            "imu_left.pb",
            "application/x-protobuf",
          )
        }
        if (zipContents.imuRight) {
          imuRightKey = await uploadToR2(
            new Blob([new Uint8Array(zipContents.imuRight)]),
            "imu_right.pb",
            "application/x-protobuf",
          )
        }
        if (zipContents.manifest) {
          const manifestData = new TextEncoder().encode(JSON.stringify(zipContents.manifest))
          manifestKey = await uploadToR2(
            new Blob([manifestData]),
            "manifest.json",
            "application/json",
          )
        }
      }

      // Phase 2: Upload compressed video via ChunkedUploader
      setUploadPhase(t("uploadingVideo"))
      const uploader = new ChunkedUploader(compressedFile, (loaded, total) => {
        setProgress(Math.round((loaded / total) * 100))
      })
      uploaderRef.current = uploader
      const videoKey = await uploader.upload()

      // Phase 3: Create session with ALL keys
      setUploadPhase(t("startingAnalysis"))
      setProgress(100)
      const session = await createSession.mutateAsync({
        element_type: "auto",
        video_key: videoKey,
        ...(imuLeftKey ? { imu_left_key: imuLeftKey } : {}),
        ...(imuRightKey ? { imu_right_key: imuRightKey } : {}),
        ...(manifestKey ? { manifest_key: manifestKey } : {}),
      })

      // Phase 4: Enqueue processing
      const processRes = await enqueueProcess({
        video_key: videoKey,
        person_click: { x: -1, y: -1 },
        session_id: session.id,
      })
      await patchSession.mutateAsync({
        id: session.id,
        body: { process_task_id: processRes.task_id },
      })

      setStep("done")
      toast.success(t("videoUploaded"))

      if (session?.id) {
        router.push(`/sessions/${session.id}`)
      }
    } catch {
      toast.error(t("uploadError"))
      setProgress(0)
      setStep("picked")
    }
  }
```

- [ ] **Step 3: Add compression UI state in the rendering section**

Add compression step rendering between `"parsing"` and `"uploading"` blocks:

```tsx
  if (step === "compressing") {
    const percent = compressionState.status === "compressing" ? compressionState.percent : 0
    return (
      <div className="mx-auto max-w-lg space-y-5 px-4 py-20">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
          <p className="mt-3 sh-display-md">{t("compressing", { percent })}</p>
        </div>
        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => { abortCompression(); setStep("picked") }}
            className="flex items-center gap-2 rounded-2xl border border-hairline px-4 py-2 text-sm text-ink-mute transition-colors hover:bg-accent"
          >
            <X className="h-4 w-4" />
            {t("cancelUpload")}
          </button>
        </div>
      </div>
    )
  }
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit 2>&1 | head -20`
Expected: no errors

- [ ] **Step 5: Manual browser test**

Run: `cd frontend && bun run dev`
Open browser, upload a video, verify:
1. "Compressing video" step appears with progress
2. Compression completes, toast shows size reduction
3. Upload proceeds with compressed file
4. Session created and analysis starts

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(app\)/upload/page.tsx
git commit -m "feat(upload): integrate video compression into upload flow"
```

---

## Wave 3: Final Verification

### Task 10: End-to-end verification

- [ ] **Step 1: Run all frontend checks**

Run: `cd frontend && bunx tsc --noEmit && bunx next lint`
Expected: PASS

- [ ] **Step 2: Run backend tests**

Run: `cd backend && uv run python -m pytest tests/ --no-cov -q`
Expected: PASS

- [ ] **Step 3: Run ML tests**

Run: `cd ml && uv run python -m pytest tests/gpu_server/ -v`
Expected: PASS (new test from Task 1)

- [ ] **Step 4: Commit final state if any fixes needed**

If any fixes were needed during verification, commit them.

---

## Self-Review

**Spec coverage:**
- Section 1 (Frontend Compression): Tasks 5-9 ✓
- Section 2 (Models in Docker): Tasks 2-4 ✓
- Section 3 (GPU Worker Cleanup): Task 1 ✓
- Section 4 (Build Pipeline): Task 4 ✓

**Placeholder scan:** No TBD/TODO/fill-in-later patterns found.

**Type consistency:** `CompressResult` defined in Task 5, used identically in Task 6 and Task 9. `CompressOptions` defined in Task 5, used in Tasks 6 and 9. `_background_init()` signature matches spec. `MOGANET_MODEL_PATH`/`YOLO_MODEL_PATH` remain unchanged.

**Review revisions applied:**
1. ✓ `mp4-demuxer` + `mp4-muxer` → `mediabunny` (single package)
2. ✓ YOLO path: `/models/yolov8n.onnx` (flat, matching server.py)
3. ✓ Docker `--mount=type=secret` + `--mount=type=cache` instead of ARG (no cache invalidation)
4. ✓ `avc1.64001F` → `isConfigSupported()` check + Baseline fallback
5. ✓ `compressVideo()` try/catch → ffmpeg.wasm runtime fallback
6. ✓ Skip heuristic (< 10 MB), 60s timeout, ZIP video extraction
7. ✓ ffmpeg.wasm `load()` with `toBlobURL()` + time-based progress
8. ✓ `/ready` detail text "models initializing"
