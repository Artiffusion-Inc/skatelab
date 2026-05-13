# Scientific Review: GPU Cold Start + Video Compression

**Date:** 2026-05-11
**Reviewed documents:**
- `docs/plans/2026-05-11-gpu-coldstart-video-compression.md`
- `docs/specs/2026-05-11-gpu-coldstart-video-compression-design.md`

**Methodology:** Six hypotheses derived from the plan/spec were tested via parallel research agents against empirical evidence (package registries, browser compatibility tables, Docker build semantics, runtime code, WASM documentation, and edge-case analysis). Each hypothesis was evaluated as CONFIRMED, PARTIALLY FALSIFIED, or FALSIFIED based on the weight of evidence.

---

## 1. Executive Summary

The plan is **partially viable**. The GPU server cleanup (Sections 2-3) is sound with one critical path bug. The frontend video compression (Section 1) contains a **fabricated API** that renders the entire WebCodecs implementation non-functional as written. The Docker build approach has a **cache invalidation defect** that negates the primary benefit of build-time model embedding.

**Verdict:** Implementation must not proceed without addressing the 3 critical bugs below. The design gaps are solvable but require non-trivial rework of the compression module and Containerfile strategy.

**Risk summary:**

| Hypothesis | Verdict | Severity |
|------------|---------|----------|
| H1: WebCodecs API feasibility | FALSIFIED | Critical |
| H2: ffmpeg.wasm fallback | Partially falsified | Moderate |
| H3: Pre-signed R2 URLs for Docker build | Partially falsified | Critical |
| H4: Containerfile model_fetch paths | FALSIFIED (bug) | Critical |
| H5: Upload flow edge cases | 6 gaps found | Moderate |
| H6: server.py cleanup safety | Confirmed | None |

---

## 2. Critical Bugs (must fix before implementation)

### 2.1. `mp4-demuxer` package does not exist (H1)

**Evidence:** Searched npm registry — no package named `mp4-demuxer` exists. The entire demuxer implementation in the plan is fiction.

**Affected locations:**
- Plan Task 5, line 419: `const { demux } = await import("mp4-demuxer")`
- Plan Task 5, line 425: `new demux.Demuxer(new demux.FileDataSource(file))`
- Plan Task 5, line 427: `demuxer.videoTracks[0]`
- Plan Task 5, line 430: `await demuxer.initialize(videoTrack)`
- Plan Task 5, line 470: `Math.ceil(demuxer.duration * options.fps)`
- Plan Task 5, line 488: `await demuxer.getNextSample(trackNumber)`
- Plan Task 5, line 577: install instruction `bun add mp4-demuxer`
- Spec Section 1, line 419: same code reference

**Impact:** The WebCodecs compression path (`compressVideoWebCodecs`) will throw `Cannot find module 'mp4-demuxer'` at runtime. The primary compression method is completely non-functional.

### 2.2. YOLO model path mismatch in Containerfile (H4)

**Evidence:** `server.py` line 58 defines `YOLO_MODEL_PATH = _PROJECT_ROOT / "data/models/yolov8n.onnx"` — flat path, no `yolo/` subdirectory. The plan places YOLO at `/models/yolo/yolov8n.onnx` (plan line 174-178, spec line 147-151). After `COPY --from=model_fetch /models/ /app/data/models/`, the file lands at `/app/data/models/yolo/yolov8n.onnx`, but `server.py` expects `/app/data/models/yolov8n.onnx`.

**Affected locations:**
- Plan Task 2, line 174: `mkdir -p /models/moganet /models/yolo`
- Plan Task 2, line 178: `curl -sS --fail -o /models/yolo/yolov8n.onnx`
- Spec Section 2, line 147: `RUN mkdir -p /models/moganet /models/yolo`
- Spec Section 2, line 151: `curl -sS -o /models/yolo/yolov8n.onnx`
- `server.py` line 58: `YOLO_MODEL_PATH = _PROJECT_ROOT / "data/models/yolov8n.onnx"`

**Impact:** At runtime, `_background_init()` raises `OSError: Model not found: /app/data/models/yolov8n.onnx`. The YOLO model is present in the image but at the wrong path. All detection and processing requests return 503.

### 2.3. Pre-signed URL cache invalidation (H3)

**Evidence:** Every `podman build` generates new pre-signed URLs (new `X-Amz-Date`, `X-Amz-Signature` query parameters). Docker layer caching uses the exact `RUN` instruction string as cache key. Since the `ARG` values (the URLs) change on every build, the `RUN curl ...` layer never hits cache. The 300 MB model download repeats on every build.

**Affected locations:**
- Plan Task 2, lines 170-178: `ARG MOGANET_MODEL_URL` / `ARG YOLO_MODEL_URL` / `RUN curl ... "${MOGANET_MODEL_URL}"`
- Plan Task 4, lines 327-332: `vastai-build` task with `--build-arg` passing URLs
- Spec Section 2, lines 143-151: same Containerfile code
- Spec Section 4, lines 240-248: build instructions

**Impact:** The stated benefit of build-time embedding ("saves 10-15 sec cold start") is correct for runtime, but the build cost is 300 MB download per build. If models are stable (infrequent updates), a pre-signed URL that changes on every CI run causes unnecessary 300 MB downloads. For a CI that builds on every push, this adds ~30-60 seconds per build and significant R2 egress cost.

---

## 3. Design Gaps (should fix for production quality)

### 3.1. `mp4-muxer` is deprecated (H1)

**Evidence:** `mp4-muxer` on npm is superseded by `mediabunny@1.44.2` (same author, actively maintained, handles entire mux+demux pipeline). The muxer APIs in the plan (`Muxer`, `ArrayBufferTarget`, `addVideoChunk`) match `mp4-muxer` but the package is unmaintained.

**Affected locations:**
- Plan Task 5, line 417: `const { Muxer, ArrayBufferTarget } = await import("mp4-muxer")`
- Plan Task 5, line 577: `bun add mp4-muxer`

**Recommendation:** Replace both `mp4-muxer` and the fictional `mp4-demuxer` with `mediabunny` (single package). APIs will need verification against `mediabunny` documentation — the plan's `Muxer`/`ArrayBufferTarget` usage may need adjustment.

### 3.2. Browser support claim is outdated (H1)

**Evidence:** Plan states "Supported: Chrome 94+, Edge 94+. Not supported: Firefox, Safari." (spec line 41, plan line 375). Firefox 130+ (Sep 2024) supports WebCodecs. Safari 16.4+ (Mar 2023) supports WebCodecs. Only Firefox Android lacks support.

**Affected locations:**
- Spec line 41: `Supported: Chrome 94+, Edge 94+. Not supported: Firefox, Safari.`
- Plan line 375-376: same claim in comment

**Impact:** The ffmpeg.wasm fallback path is triggered unnecessarily for Firefox desktop and Safari users. This causes ~30 MB WASM download and 1-3 minute compression time where WebCodecs would work in seconds.

### 3.3. `avc1.64001F` codec requires hardware encoder (H1)

**Evidence:** `avc1.64001F` is H.264 High Profile. Chrome's software fallback (OpenH264) only supports Baseline Profile (`avc1.42001E`). On devices without hardware H.264 encoder (some low-end laptops, older desktops), `VideoEncoder.configure()` will throw `NotSupportedError`.

**Affected locations:**
- Plan Task 5, line 460: `codec: "avc1.64001F"`
- Spec line 50: `codec: 'avc1.64001F'`

**Recommendation:** Add codec support check before configure:

```typescript
// Try High Profile, fall back to Baseline
const codec = (await VideoEncoder.isConfigSupported({
  codec: "avc1.64001F", width: outW, height: outH, bitrate: options.bitrate, framerate: options.fps
})).supported ? "avc1.64001F" : "avc1.42001E"
```

### 3.4. ffmpeg.wasm `load()` cross-origin failure (H2)

**Evidence:** `ffmpeg.load()` without arguments loads core from CDN via Web Worker. Cross-origin Worker creation is blocked by some browser configurations. Must use `toBlobURL()` to convert CDN resources to same-origin blob URLs.

**Affected locations:**
- Plan Task 5, line 530: `await ffmpeg.load()`

**Recommendation:**
```typescript
const baseURL = "https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd"
await ffmpeg.load({
  coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
  wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
  workerURL: await toBlobURL(`${baseURL}/ffmpeg-core.worker.js`, "text/javascript"),
})
```

### 3.5. ffmpeg.wasm progress callback is inaccurate (H2)

**Evidence:** The `progress` field (0-1 ratio) is inaccurate when input/output duration differs (which is the case when resampling from 60fps to 30fps). Use the `time` field (microseconds elapsed) for accurate progress.

**Affected locations:**
- Plan Task 5, lines 534-536:
  ```typescript
  ffmpeg.on("progress", ({ progress }) => {
    options.onProgress(Math.round(progress * 100))
  })
  ```

**Recommendation:** Use `time` field divided by known input duration:
```typescript
ffmpeg.on("progress", ({ time }) => {
  // time is in microseconds, inputDuration in seconds
  const percent = Math.min(Math.round((time / 1e6 / inputDuration) * 100), 99)
  options.onProgress(percent)
})
```

### 3.6. Only single-thread ffmpeg.wasm works reliably (H2)

**Evidence:** Multi-thread `@ffmpeg/core-mt` hangs on Safari and Chromium when using `-vf scale`. Single-thread version (`@ffmpeg/core`) does not require SharedArrayBuffer (no `Cross-Origin-Opener-Policy` / `Cross-Origin-Embedder-Policy` headers needed) and works across all browsers.

**Affected locations:** Plan does not specify `@ffmpeg/core-mt`, but does not explicitly recommend single-thread either. Implicit risk of a developer installing the MT variant.

**Recommendation:** Explicitly document: use `@ffmpeg/core` (single-thread) only. Do NOT use `@ffmpeg/core-mt`. Add comment in `video-compression.ts`.

### 3.7. ffmpeg.wasm GPL-2.0-or-later license (H2)

**Evidence:** `@ffmpeg/core` includes libx264 (GPL-2.0-or-later). This is a copyleft license. If the application is distributed, legal review is needed to confirm compliance. For a SaaS where the WASM runs client-side in the user's browser, the license implications require legal assessment.

**Affected locations:** Plan Task 5, line 577: `bun add @ffmpeg/ffmpeg @ffmpeg/util`

**Recommendation:** Flag for legal review. Consider `@ffmpeg/core` without libx264 (LGPL build) if available, which would limit encoding to `libvpx` (VP8/VP9) — less compatible with the H.264 requirement. Alternative: use WebCodecs as primary (now broader support) and only ship ffmpeg.wasm LGPL variant.

### 3.8. No runtime fallback when WebCodecs fails mid-stream (H5)

**Evidence:** If WebCodecs encoding fails partway (e.g., codec not supported, OOM), the user receives an error with no automatic retry via ffmpeg.wasm. The decision logic (plan lines 563-571) only checks at entry — once WebCodecs is selected, there is no fallback on failure.

**Affected locations:**
- Plan Task 5, lines 563-571: `compressVideo()` function
- Plan Task 9: upload flow integration

**Recommendation:** Add try/catch with fallback in `compressVideo()`:
```typescript
export async function compressVideo(file: File, opts: CompressOptions = {}): Promise<CompressResult> {
  if (isWebCodecsSupported()) {
    try {
      return await compressVideoWebCodecs(file, opts)
    } catch (e) {
      console.warn("WebCodecs failed, falling back to ffmpeg.wasm:", e)
    }
  }
  return compressVideoFFmpeg(file, opts)
}
```

### 3.9. Already-compressed videos cause generation loss (H5)

**Evidence:** The plan compresses ALL video files before upload. A 5 MB 720p30 MP4 (already within target parameters) will be re-encoded, causing generation loss (degraded keypoint detection quality) with minimal size savings.

**Affected locations:**
- Plan Task 9, lines 866-875: compression applied unconditionally to non-ZIP files
- Spec Section 1, line 96: "Frontend compresses (progress bar shown)"

**Recommendation:** Add a skip heuristic:
```typescript
function shouldCompress(file: File, video?: HTMLVideoElement): boolean {
  // Skip if already small enough
  if (file.size < 10 * 1024 * 1024) return false  // < 10 MB
  // Skip if already low resolution + low FPS
  if (video && video.videoWidth <= 1280 && video.videoHeight <= 720) return false
  return true
}
```

### 3.10. Very short videos (<1s) produce empty MP4 (H5)

**Evidence:** When `frame.duration === 0` (common for very short videos or single-frame clips), the WebCodecs encoder silently skips frames, producing an empty MP4 output.

**Affected locations:**
- Plan Task 5, line 474: `if (frame.duration) { encoder.encode(...) }` — frames with duration=0 are skipped

**Recommendation:** Assign a minimum duration when `frame.duration === 0`:
```typescript
const duration = frame.duration || (1_000_000 / options.fps)  // default to 1/fps in microseconds
encoder.encode(frame, { keyFrame: frameCount % 30 === 0 })
```

### 3.11. ZIP-extracted videos not compressed (H5)

**Evidence:** The plan explicitly skips compression for ZIP files (plan Task 9, lines 869-871: `if (!isZipFile(file))`). But ZIP-extracted videos from the mobile app are 32+ MB and need compression as much as standalone files.

**Affected locations:**
- Plan Task 9, line 871: `if (!isZipFile(file))` — skips ZIP files entirely

**Recommendation:** Compress the video extracted from the ZIP, not the ZIP itself:
```typescript
const videoFile = zipContents?.video ?? file
if (videoFile.size > 10 * 1024 * 1024) {  // only compress if > 10 MB
  const result = await compress(videoFile)
  // ...
}
```

### 3.12. 4K60 video crashes ffmpeg.wasm on mobile (H5)

**Evidence:** 4K60 video requires ~1 GB WASM memory for ffmpeg.wasm. Most mobile browsers limit WASM memory to 256-512 MB. No max input resolution check exists.

**Affected locations:** Plan Task 5, Task 9 — no resolution check before compression

**Recommendation:** Add max input resolution guard:
```typescript
if (video.videoWidth > 3840 || video.videoHeight > 2160) {
  // Reject or warn — ffmpeg.wasm will likely crash
  throw new Error("Video resolution too high for browser compression. Please use a lower-resolution recording.")
}
```

### 3.13. No compression timeout (H5)

**Evidence:** i18n key `compressionSkip` exists (plan Task 7) but is unused in the upload flow. On a slow phone, ffmpeg.wasm compression can take 1-3 minutes. No auto-timeout or skip mechanism exists. User sees stuck progress bar.

**Affected locations:**
- Plan Task 7, line 763: `"compressionSkip": "Пропустить сжатие"` — key defined but never used
- Plan Task 9: no timeout logic

**Recommendation:** Add a 60-second timeout with skip option:
```typescript
const compressionPromise = compress(videoFile, { onProgress: ... })
const timeoutPromise = new Promise((_, reject) =>
  setTimeout(() => reject(new Error("Compression timeout")), 60_000)
)
try {
  result = await Promise.race([compressionPromise, timeoutPromise])
} catch {
  // Fall back to uncompressed upload
  toast.info(t("compressionSkip"))
  result = { blob: videoFile, originalSize: videoFile.size, compressedSize: videoFile.size }
}
```

---

## 4. Minor Issues (nice to fix)

### 4.1. ffmpeg.wasm WASM size is 30.7 MB, not ~25 MB (H2)

**Evidence:** `@ffmpeg/core` UMD WASM file is 30.7 MB uncompressed. Compressed transfer size is ~8-12 MB. The plan states "~25 MB WASM" (plan line 376, spec line 64).

**Affected locations:**
- Plan line 376: `Loads ~25 MB WASM on first call`
- Spec line 64: `Load on-demand (~25 MB WASM)`

**Correction:** State "30.7 MB WASM (~8-12 MB compressed transfer)".

### 4.2. `/ready` endpoint detail text becomes misleading (H6)

**Evidence:** After cleanup, `_background_init()` only verifies models exist (no download). But `/ready` (server.py line 156) still says `"detail": "models downloading"`. This is misleading — models are not downloading, they are being verified.

**Affected locations:**
- `server.py` line 156: `return {"status": "initializing", "detail": "models downloading"}`

**Recommendation:** Change to `"detail": "models initializing"` or `"detail": "verifying models"`.

### 4.3. Pre-existing bug: `_background_init()` failure is permanent (H6)

**Evidence:** If `_background_init()` fails (e.g., model file corrupted), `_models_ready` stays `False` forever. No retry mechanism exists. All subsequent requests return 503 until the container is restarted.

**Affected locations:**
- `server.py` lines 114-135: `_background_init()` sets `_models_ready = False` on exception, never retries

**Recommendation:** Add a retry counter or periodic re-check. Out of scope for this plan but worth noting.

### 4.4. Special characters in pre-signed URLs need shell protection (H3)

**Evidence:** Pre-signed URLs contain `&` and `?` characters. In Containerfile `RUN` commands, these must be double-quoted: `"${VAR}"`. The plan already uses quotes (plan line 177-178), so this is handled correctly. Noting for completeness.

### 4.5. URL exposure in `docker history` (H3)

**Evidence:** Build args (including pre-signed URLs) are visible in `docker history`. Since URLs expire in 1 hour, risk is low. But for defense in depth, `--mount=type=secret` would keep URLs out of image metadata entirely.

---

## 5. Confirmed Safe (hypotheses that passed)

### 5.1. Moganet model path is correct (H4)

**Evidence:** Plan puts Moganet at `/models/moganet/moganet_b_ap2d_384x288.onnx`. After `COPY --from=model_fetch /models/ /app/data/models/`, file lands at `/app/data/models/moganet/moganet_b_ap2d_384x288.onnx`. `server.py` line 57: `MOGANET_MODEL_PATH = _PROJECT_ROOT / "data/models/moganet/moganet_b_ap2d_384x288.onnx"` — match confirmed.

### 5.2. `_async_session` still needed (H6)

**Evidence:** `_async_session` (server.py line 67) is used by `_s3()` (server.py line 228) for per-request R2 I/O. Cannot be removed during cleanup. Plan correctly states to keep it (plan line 136).

### 5.3. `aiobotocore` import must stay (H6)

**Evidence:** `aiobotocore` is imported at server.py line 18 and used by `_s3()` via `_async_session.create_client()`. Must remain even after removing model download code.

### 5.4. R2 env vars for model download are safe to remove from server.py (H6)

**Evidence:** `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` env vars are only used in `_download_models_from_r2()` (server.py lines 72-75). Per-request R2 credentials come from `DetectRequest`/`ProcessRequest` fields. Safe to remove the env var reads from server.py.

### 5.5. Pre-signed R2 URLs fully compatible with R2 (H3)

**Evidence:** Cloudflare documentation confirms `boto3.generate_presigned_url` works with R2 GET operations. URL length (~400-600 chars) is well within Containerfile limits.

### 5.6. `mkdir` + `COPY` merge behavior is correct (H4)

**Evidence:** Docker `COPY` merges into existing directories. `mkdir -p /app/data/models` followed by `COPY --from=model_fetch /models/ /app/data/models/` works correctly.

### 5.7. Permissions are correct (H4)

**Evidence:** `mkdir` + `chown` in the runtime stage sets ownership, and `COPY --chown=appuser:appuser` maintains it. No permission issue.

### 5.8. ChunkedUploader + Blob File compatibility is safe (H5)

**Evidence:** `ChunkedUploader` accepts `File` and `Blob` objects. `new File([result.blob], ...)` creates a valid File from a Blob. No compatibility issue.

### 5.9. Content-Type compatibility is safe (H5)

**Evidence:** `new Blob([buffer], { type: "video/mp4" })` and `new File([result.blob], ..., { type: "video/mp4" })` set correct Content-Type. ChunkedUploader preserves this. No issue.

### 5.10. `worker.py` `on_load` signal match (H6)

**Evidence:** Backend worker's `on_load` checks for "Background init complete" as substring of the log message. After cleanup, the log message is "Background init complete — models ready" (plan line 126). The substring match still works.

---

## 6. Recommended Revisions

### Revision 1: Replace `mp4-demuxer` + `mp4-muxer` with `mediabunny`

**Applies to:** Plan Task 5 (lines 370-572), Spec Section 1 (lines 39-83)

**Change:**
1. Remove `mp4-demuxer` and `mp4-muxer` from dependencies (plan line 577, spec install step).
2. Add `mediabunny` as single dependency: `bun add mediabunny`.
3. Rewrite `compressVideoWebCodecs()` using `mediabunny` APIs. The exact API surface needs verification against `mediabunny@1.44.2` documentation, but the high-level flow (demux → decode → resize → encode → mux) remains the same.
4. Update browser support text (spec line 41, plan line 375): "Chrome 94+, Edge 94+, Firefox 130+, Safari 16.4+. Fallback: ffmpeg.wasm for Firefox Android."

### Revision 2: Fix YOLO model path in Containerfile

**Applies to:** Plan Task 2 (lines 174-178), Spec Section 2 (lines 147-151)

**Change:** Replace:
```dockerfile
RUN mkdir -p /models/moganet /models/yolo && \
    curl -sS --fail -o /models/yolo/yolov8n.onnx \
      "${YOLO_MODEL_URL}"
```
With:
```dockerfile
RUN mkdir -p /models/moganet /models/yolo && \
    curl -sS --fail -o /models/moganet/moganet_b_ap2d_384x288.onnx \
      "${MOGANET_MODEL_URL}" && \
    curl -sS --fail -o /models/yolov8n.onnx \
      "${YOLO_MODEL_URL}"
```

Note: YOLO goes to `/models/yolov8n.onnx` (flat), not `/models/yolo/yolov8n.onnx`. The `/models/yolo` directory is created but unused — can be removed from the `mkdir` command, or kept if future models need subdirectories.

### Revision 3: Replace `ARG`-based pre-signed URLs with `--mount=type=secret` + `--mount=type=cache`

**Applies to:** Plan Task 2 (lines 162-187), Spec Section 2 (lines 133-159), Plan Task 4 (lines 317-344), Spec Section 4 (lines 239-249)

**Change:** Replace the `ARG` + `RUN curl` approach with Docker secrets and cache mounts:

```dockerfile
# Stage 2: model download
FROM docker.io/python:3.11-slim AS model_fetch

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Secret files containing pre-signed URLs (one per line)
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

Build command changes to:
```bash
podman build \
  --secret id=moganet_url,src=/tmp/moganet_url.txt \
  --secret id=yolo_url,src=/tmp/yolo_url.txt \
  -f ml/gpu_server/Containerfile \
  -t ghcr.io/Artiffusion-Inc/skatelab-worker:latest .
```

**Benefits:** (1) URLs not stored in image metadata. (2) `--mount=type=cache` persists model files across builds — 300 MB models downloaded once, reused from cache on subsequent builds. (3) Cache key is the filename, not the URL — no cache invalidation on URL rotation.

### Revision 4: Add codec support check with Baseline fallback

**Applies to:** Plan Task 5 (line 460), Spec Section 1 (line 50)

**Change:** Before `encoder.configure()`, check codec support:
```typescript
// Check hardware encoder support
const preferredCodec = "avc1.64001F"  // High Profile
const fallbackCodec = "avc1.42001E"   // Baseline Profile

const supportCheck = await VideoEncoder.isConfigSupported({
  codec: preferredCodec,
  width: outW,
  height: outH,
  bitrate: options.bitrate,
  framerate: options.fps,
})
const codec = supportCheck.supported ? preferredCodec : fallbackCodec

encoder.configure({
  codec,
  width: outW,
  height: outH,
  bitrate: options.bitrate,
  framerate: options.fps,
  latencyMode: "quality",
})
```

### Revision 5: Add WebCodecs → ffmpeg.wasm runtime fallback

**Applies to:** Plan Task 5 (lines 563-571)

**Change:** Wrap WebCodecs in try/catch with automatic fallback:
```typescript
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

### Revision 6: Add compression skip heuristic + timeout

**Applies to:** Plan Task 9 (lines 860-960)

**Change:**
1. Skip compression for files < 10 MB or already at target resolution/fps.
2. Add 60-second timeout with skip fallback.
3. Compress ZIP-extracted video, not skip all ZIPs.

```typescript
async function handleUpload() {
  // ...
  const videoFile = zipContents?.video ?? file

  let compressedFile: File = videoFile
  if (videoFile.size > 10 * 1024 * 1024) {
    try {
      const result = await Promise.race([
        compress(videoFile, { onProgress: ... }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("timeout")), 60_000)
        ),
      ])
      compressedFile = new File([result.blob], `compressed.mp4`, { type: "video/mp4" })
      toast.success(t("compressionDone", { ... }))
    } catch {
      toast.info(t("compressionSkip"))
    }
  }
  // ...
}
```

### Revision 7: Fix ffmpeg.wasm initialization

**Applies to:** Plan Task 5 (lines 528-530)

**Change:**
```typescript
const { FFmpeg } = await import("@ffmpeg/ffmpeg")
const { fetchFile, toBlobURL } = await import("@ffmpeg/util")

const ffmpeg = new FFmpeg()
const baseURL = "https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd"
await ffmpeg.load({
  coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
  wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
  workerURL: await toBlobURL(`${baseURL}/ffmpeg-core.worker.js`, "text/javascript"),
})
```

### Revision 8: Update `/ready` endpoint detail text

**Applies to:** `server.py` line 156 (after cleanup)

**Change:** Replace `"detail": "models downloading"` with `"detail": "models initializing"`.

---

## Appendix: Hypothesis-Verdict Summary

| # | Hypothesis | Verdict | Key Finding |
|---|-----------|---------|-------------|
| H1 | WebCodecs API feasibility | FALSIFIED | `mp4-demuxer` does not exist; `mp4-muxer` deprecated; browser support outdated; codec risk |
| H2 | ffmpeg.wasm fallback | Partially falsified | Size wrong, `load()` needs args, progress inaccurate, ST only, GPL license |
| H3 | Pre-signed R2 URLs for Docker build | Partially falsified | Cache invalidation defeats purpose; `--mount=type=secret+cache` is better |
| H4 | Containerfile model_fetch paths | FALSIFIED (bug) | YOLO path mismatch — `/models/yolo/yolov8n.onnx` vs expected `data/models/yolov8n.onnx` |
| H5 | Upload flow edge cases | 6 gaps found | No runtime fallback, no skip heuristic, short video bug, ZIP gap, 4K memory, no timeout |
| H6 | server.py cleanup safety | Confirmed | Safe with minor text fix to `/ready` endpoint; note permanent failure bug |