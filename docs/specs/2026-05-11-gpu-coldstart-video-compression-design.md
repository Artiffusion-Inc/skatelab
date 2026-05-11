# GPU Cold Start + Video Compression Design

**Date:** 2026-05-11
**Status:** Draft

## Problem

1. **Cold start too slow**: Vast.ai PyWorker downloads ONNX models from R2 at startup (~300 MB, 10-15 sec). Total cold start: 25-30 sec. Target: < 30 sec, ideally < 10 sec.
2. **Video files too large**: 16-sec mobile video = 32+ MB. R2 storage + GPU download = expensive and slow. Target: 6-10x compression (3-5 MB for 16 sec).
3. **Warm worker in future**: Need design that works for both PyWorker cold start and persistent warm worker.

## Solution Overview

1. **Frontend compression** — compress video before upload (WebCodecs API, ffmpeg.wasm fallback)
2. **Models in Docker image** — embed ONNX models at build time, no R2 download at startup
3. **Clean up GPU server** — remove model download code, simplify startup

## Section 1: Frontend Video Compression

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|----------|
| Codec | H.264 (libx264 / AVC) | Universal, GPU-decodable |
| Max width | 1280px (aspect preserved) | Sufficient for pose estimation (MogaNet input: 384x288) |
| FPS | 30 | Agreed: interpolate if needed |
| CRF | 28 | Good quality/size balance for pose estimation |
| Pixel format | yuv420p 8-bit | Standard compatibility |
| Audio | Strip | Not needed for ML pipeline |

### Expected compression

| Input | Output | Ratio |
|-------|--------|-------|
| 16 sec, 1080p60, 32 MB | 16 sec, 720p30, ~3-4 MB | 8-10x |
| 30 sec, 1080p30, 60 MB | 30 sec, 720p30, ~6-8 MB | 8-10x |
| 16 sec, 4K60, 120 MB | 16 sec, 720p30, ~3-4 MB | 30x |

### Implementation: WebCodecs API (primary)

Supported: Chrome 94+, Edge 94+. Not supported: Firefox, Safari.

```typescript
// Pseudocode — frontend compression
async function compressVideo(file: File, options: CompressOptions): Promise<Blob> {
  const decoder = new VideoDecoder({ output: onFrame, error: onError });
  const encoder = new VideoEncoder({ output: onChunk, error: onError });

  encoder.configure({
    codec: 'avc1.64001F',  // H.264 High profile
    width: options.maxWidth,
    height: options.maxHeight,
    bitrate: 2_000_000,    // 2 Mbps target
    framerate: 30,
  });

  // Demux → decode → resize → encode → mux
  // Output: MP4 container with H.264
}
```

### Implementation: ffmpeg.wasm (fallback)

For Firefox/Safari. Load on-demand (~25 MB WASM).

```typescript
async function compressVideoFFmpeg(file: File): Promise<Blob> {
  const ffmpeg = new FFmpeg();
  await ffmpeg.load();
  await ffmpeg.writeFile('input.mp4', await fetchFile(file));
  await ffmpeg.exec([
    '-i', 'input.mp4',
    '-vf', 'scale=1280:-2',
    '-r', '30',
    '-c:v', 'libx264',
    '-crf', '28',
    '-an',          // strip audio
    '-pix_fmt', 'yuv420p',
    'output.mp4',
  ]);
  return await ffmpeg.readFile('output.mp4');
}
```

### Decision logic

```
if (typeof VideoDecoder !== 'undefined') → WebCodecs
else → ffmpeg.wasm
```

### Upload flow changes

1. User selects file in DropZone
2. Frontend compresses (progress bar shown)
3. Compressed file sent via existing ChunkedUploader
4. Original file NOT stored — only compressed version in R2
5. Max upload size reduced: 500 MB → 50 MB (compressed)

### Existing normalize_video.py

`ml/scripts/normalize_video.py` already implements equivalent compression:
- H.264, max 1280px, 30 fps, CRF 23, preset fast
- Used in CLI/Gradio workflows

No changes needed to this script. It serves as server-side fallback for direct API users (CLI).

## Section 2: Models in Docker Image

### Current flow (slow)

```
PyWorker creates container → uvicorn starts → _background_init()
  → _download_models_from_r2()  # 300 MB download, 10-15 sec
  → CUDA warmup
  → _models_ready = True
```

### New flow (fast)

```
docker build → models downloaded from R2 (build-time, Docker secret)
PyWorker creates container → uvicorn starts → _background_init()
  → verify models exist (stat, <1ms)
  → CUDA warmup
  → _models_ready = True
```

### Containerfile changes

Uses **pre-signed URLs** (Option C). CI generates time-limited URLs, passes as build args. No R2 credentials in image, no AWS CLI needed.

```dockerfile
# Stage 1: builder — unchanged (deps install)

# Stage 2: model download (new stage)
FROM docker.io/python:3.11-slim AS model_fetch

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pre-signed URLs — generated at build time, expire in 1h
ARG MOGANET_MODEL_URL
ARG YOLO_MODEL_URL

RUN mkdir -p /models/moganet /models/yolo && \
    curl -sS -o /models/moganet/moganet_b_ap2d_384x288.onnx \
      "${MOGANET_MODEL_URL}" && \
    curl -sS -o /models/yolo/yolov8n.onnx \
      "${YOLO_MODEL_URL}"

# Stage 3: runtime
FROM docker.io/python:3.11-slim
# ... existing setup ...

# Copy models from fetch stage
COPY --from=model_fetch --chown=appuser:appuser /models/ /app/data/models/
```

### server.py changes

Remove from `server.py`:

1. `_download_models_from_r2()` — delete
2. `_R2_MODELS` list — delete
3. R2 env vars for model download — delete
4. `_background_init()` — simplify: only CUDA warmup + verify model files exist
5. R2 env vars in Containerfile for model download — remove

Keep:
- `_models_ready` flag
- `_background_init()` (simplified: verify + CUDA warmup only)
- Per-request R2 credentials in `DetectRequest`/`ProcessRequest` (for video I/O)

### Image size impact

| Component | Before | After |
|-----------|--------|-------|
| Base image | ~150 MB | ~150 MB |
| Python venv | ~800 MB | ~800 MB |
| CUDA pip libs | ~3.8 GB | ~3.8 GB |
| ONNX models | 0 (downloaded at runtime) | ~300 MB (embedded) |
| **Total** | ~4.9 GB | ~5.2 GB |

+300 MB image, but saves 10-15 sec cold start. Acceptable tradeoff.

## Section 3: GPU Worker Cleanup

### Remove

- `_download_models_from_r2()` and related code
- `_R2_MODELS` list
- R2 credential env vars for model download
- Startup env vars: `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` (used only for model download)

### Simplify `_background_init()`

```python
async def _background_init():
    global _models_ready
    try:
        # Verify models exist
        if not MOGANET_MODEL_PATH.exists():
            raise OSError(f"Model not found: {MOGANET_MODEL_PATH}")
        if not YOLO_MODEL_PATH.exists():
            raise OSError(f"Model not found: {YOLO_MODEL_PATH}")

        # CUDA warmup
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

### Keep unchanged

- `/detect` endpoint (preview + person detection)
- `/process` endpoint (pose extraction + metrics)
- `/health`, `/ping`, `/ready`, `/metrics`
- Per-request R2 credentials for video download/upload
- Prometheus metrics
- `_s3()`, `_s3_download()`, `_s3_upload()`

## Section 4: Build Pipeline

### How to build with pre-signed URLs

```bash
# 1. Generate pre-signed URLs (CI script, expires in 1h)
python scripts/generate_model_presigned_urls.py --output urls.json

# 2. Build with URLs as build args
podman build \
  --build-arg MOGANET_MODEL_URL=$(jq -r .moganet urls.json) \
  --build-arg YOLO_MODEL_URL=$(jq -r .yolo urls.json) \
  -t ghcr.io/artiffusion-inc/skatelab-worker:latest \
  -f ml/gpu_server/Containerfile .
```

### CI integration

Add to `Taskfile.yaml`:

```yaml
vastai-build:
  desc: "Build GPU worker image with embedded models"
  cmds:
    - python scripts/generate_model_presigned_urls.py --output /tmp/model_urls.json
    - podman build
        --build-arg MOGANET_MODEL_URL=$(jq -r .moganet /tmp/model_urls.json)
        --build-arg YOLO_MODEL_URL=$(jq -r .yolo /tmp/model_urls.json)
        -t ghcr.io/artiffusion-inc/skatelab-worker:latest
        -f ml/gpu_server/Containerfile .
```

## Summary of Changes

| Component | Change | Impact |
|-----------|--------|--------|
| Frontend (DropZone) | Add video compression before upload | 6-10x smaller uploads |
| Frontend (DropZone) | Reduce max upload size 500→50 MB | Faster uploads |
| Containerfile | Add model_fetch stage, embed ONNX models | +300 MB image, -15 sec cold start |
| Containerfile | Remove R2 model-download env vars | Cleaner config |
| server.py | Remove `_download_models_from_r2()` | Simpler startup |
| server.py | Simplify `_background_init()` | Faster startup |
| Build pipeline | New task `vastai-build` with pre-signed URLs | Reproducible builds |

## Out of Scope

- Backend video normalization (frontend does it)
- GPU inference speedup (separate concern)
- Multi-GPU processing
- Warm worker auto-scaling
